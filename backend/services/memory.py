"""Person B's authorized ingestion, human review and state read interfaces."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from backend.ai.deduplication import match_key
from backend.ai.extractor import GeminiExtractor
from backend.ai.retrieval import COLLECTIONS, project_state
from backend.database.supabase_client import SupabaseMemoryStore
from backend.models.schemas import EmailPayload, ExtractedItem, IngestionResponse, ProjectState

TRANSITIONS = {
    "open": {"in_progress", "blocked"},
    "in_progress": {"implemented", "blocked"},
    "blocked": {"open", "in_progress", "implemented"},
    "implemented": {"verified"},
    "verified": set(),
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def find_record(snapshot, kind, title):
    key = match_key(title)
    return next(
        (record for record in snapshot[COLLECTIONS[kind]]
         if record["match_key"] == key and record.get("state") != "superseded"),
        None,
    )


def evidence_row(source, quote, kind):
    start = source["body"].find(quote)
    if not quote.strip() or start < 0:
        raise ValueError("Evidence must match a contiguous span in the original body")
    return {
        "evidence_id": str(uuid4()), "source_id": source["source_id"],
        "source_type": source["source_type"], "kind": kind,
        "quote": quote, "start": start, "end": start + len(quote),
    }


def add_evidence(record, row, timestamp):
    record["evidence"].append({
        **{key: row[key] for key in ("evidence_id", "source_id", "kind")},
        "excerpt": row["quote"][:240],
    })
    record["updated_at"] = timestamp


def new_record(snapshot, kind, item, timestamp):
    record = {
        "id": str(uuid4()), "match_key": match_key(item.title),
        "updated_at": timestamp, "evidence": [],
    }
    if kind == "deliverable":
        record.update(title=item.title, description=item.description, status="open", blocked_reason=None)
    elif kind == "question":
        record.update(question=item.title, state="open", requires_client_consent=True,
                      answer=None, answered_source_id=None)
    else:
        record.update(statement=item.description, state="active", supersedes_id=None)
    snapshot[COLLECTIONS[kind]].append(record)
    return record


class MemoryService:
    """Call only after authorizing the project. Reviews require an authenticated human."""

    def __init__(self, store, extract: Callable[[EmailPayload], list[ExtractedItem]] | None = None):
        self.store = store
        self.extract = extract

    def _read(self, project_id):
        snapshot = self.store.read(project_id)
        if snapshot is None:
            raise LookupError("Unknown project")
        return snapshot

    def get_project_state(self, project_id: str) -> ProjectState:
        return project_state(self._read(project_id))

    def _source(self, source_type, source_id, project_id):
        if hasattr(self.store, "source_for_project"):
            return self.store.source_for_project(source_type, source_id, project_id)
        return self.store.source(source_type, source_id)

    def ingest_email(self, email: EmailPayload, *, approved_items=None) -> IngestionResponse:
        self._read(email.project_id)
        existing = self._source(email.source_type, email.source_id, email.project_id)
        if existing:
            if existing["project_id"] != email.project_id:
                raise PermissionError("Source already belongs to another project")
            return IngestionResponse(status="already_processed", source_id=email.source_id)

        items = approved_items
        if items is None:
            extract = self.extract or GeminiExtractor.from_env()
            items = extract(email)
        source = email.model_dump(mode="json")
        valid = []
        for item in items:
            if (item.source_id == email.source_id and match_key(item.title)
                    and item.source_quote.strip() and item.source_quote in email.body):
                valid.append(item)

        for _ in range(5):
            snapshot = self._read(email.project_id)
            before = project_state(snapshot)
            timestamp = now()
            rows = []
            seen = set()
            for item in valid:
                identity = item.model_dump_json()
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(self._reconcile(snapshot, source, item, timestamp))
            status = self._commit(snapshot, before, source, rows, {
                "action": "ingested", "source_id": email.source_id,
                "invalid_items": len(items) - len(valid),
            })
            if status == "foreign_source":
                raise PermissionError("Source already belongs to another project")
            if status != "retry":
                return IngestionResponse(status=status, source_id=email.source_id)
        raise RuntimeError("Concurrent project updates prevented ingestion")

    def _commit(self, snapshot, before, source, evidence, event):
        after = project_state(snapshot)
        event["state_changed"] = before != after
        return self.store.commit(
            before.project_id, snapshot["revision"], snapshot, source, evidence, event
        )

    def _reconcile(self, snapshot, source, item, timestamp):
        kind = "deliverable" if item.type in {"concern", "qa_result"} else item.type
        record = find_record(snapshot, kind, item.title)
        proposed = item.proposed_status
        repeated = record is not None and (
            proposed is None or (kind == "deliverable" and proposed == record["status"])
        )
        needs_review = (
            item.requires_review or item.type in {"concern", "qa_result", "decision"}
            or (not repeated and proposed is not None and (record is not None or proposed != "open"))
        )
        row = evidence_row(source, item.source_quote, "requirement")
        if needs_review:
            snapshot["reviews"].append({
                "id": str(uuid4()), "item_type": kind,
                "item_id": record["id"] if record else None,
                "reason": "Human review required for the proposed change.",
                "proposed_change": item.description.strip() or item.title,
                "created_at": timestamp, "evidence": [{
                    **{key: row[key] for key in ("evidence_id", "source_id", "kind")},
                    "excerpt": row["quote"][:240],
                }],
                "status": "pending", "proposal": item.model_dump(mode="json"),
            })
        else:
            if record is None:
                record = new_record(snapshot, kind, item, timestamp)
            add_evidence(record, row, timestamp)
        return row

    def list_pending_reviews(self, project_id: str) -> list[dict]:
        """Return internal proposals for the authorized human review workflow."""
        return [
            review for review in self._read(project_id)["reviews"]
            if review["status"] == "pending"
        ]

    def resolve_review(self, project_id: str, review_id: str, *, reviewer: str,
                       approve: bool, qa_passed: bool = False) -> ProjectState:
        """Approve a single source-backed change after inspecting its original evidence."""
        if not reviewer.strip():
            raise ValueError("Reviewer identity is required")
        for _ in range(5):
            snapshot = self._read(project_id)
            before = project_state(snapshot)
            review = next(
                (entry for entry in snapshot["reviews"] if entry["id"] == review_id), None
            )
            if review is None:
                raise LookupError("Unknown review")
            if review["status"] != "pending":
                if review["status"] == ("approved" if approve else "rejected"):
                    return before
                raise ValueError("Review was already resolved")
            timestamp = now()
            rows = []
            if approve:
                rows.append(self._approve(snapshot, review, timestamp, qa_passed))
            review.update(status="approved" if approve else "rejected",
                          reviewer=reviewer, resolved_at=timestamp)
            status = self._commit(snapshot, before, None, rows, {
                "action": "review_resolved", "review_id": review_id,
                "reviewer": reviewer, "approved": approve,
            })
            if status != "retry":
                return self.get_project_state(project_id)
        raise RuntimeError("Concurrent project updates prevented review resolution")

    def _approve(self, snapshot, review, timestamp, qa_passed):
        item = ExtractedItem.model_validate(review["proposal"])
        source = self._source("email", item.source_id, snapshot["project_id"])
        if source is None or source["project_id"] != snapshot["project_id"]:
            raise ValueError("Review source is outside the project")
        kind = review["item_type"]
        record = find_record(snapshot, kind, item.title)
        if review["item_id"] is not None and (record is None or record["id"] != review["item_id"]):
            raise ValueError("Review target changed. Submit a new proposal.")
        if review["item_id"] is None and record is not None:
            raise ValueError("A matching record now exists. Submit a new proposal.")

        if item.type == "qa_result" and (
            record is None or item.proposed_status != "verified"
            or record["status"] != "implemented" or not qa_passed
        ):
            raise ValueError("Verification requires implemented work and a human-confirmed passing QA result")

        evidence_kind = "requirement"
        if kind == "deliverable":
            status = item.proposed_status
            if record is None:
                record = new_record(snapshot, kind, item, timestamp)
            if status is not None and status != record["status"]:
                if status not in TRANSITIONS[record["status"]]:
                    raise ValueError("Invalid deliverable status transition")
                if status == "verified":
                    if item.type != "qa_result" or not qa_passed:
                        raise ValueError("Verification requires a human-confirmed passing QA result")
                    evidence_kind = "qa_result"
                elif status == "implemented":
                    evidence_kind = "implementation"
                record.update(status=status, blocked_reason=item.description if status == "blocked" else None)
        elif kind == "question":
            if item.proposed_status == "answered":
                if (record is None or record["state"] != "open" or not item.description.strip()
                        or source["sender"].casefold() not in snapshot["client_senders"]):
                    raise ValueError("An open question and an authorized client answer are required")
                evidence_kind = "client_answer"
                record.update(state="answered", answer=item.description, answered_source_id=item.source_id)
            elif item.proposed_status in {None, "open"}:
                if record is None:
                    record = new_record(snapshot, kind, item, timestamp)
            else:
                raise ValueError("Invalid question status transition")
        else:
            if not item.description.strip():
                raise ValueError("An approved decision needs a statement")
            evidence_kind = "decision"
            if record is None or record["statement"] != item.description:
                previous = record
                record = new_record(snapshot, kind, item, timestamp)
                if previous is not None:
                    previous.update(state="superseded", updated_at=timestamp)
                    record["supersedes_id"] = previous["id"]

        row = evidence_row(source, item.source_quote, evidence_kind)
        add_evidence(record, row, timestamp)
        return row


def ingest_email(email: EmailPayload) -> IngestionResponse:
    return MemoryService(SupabaseMemoryStore.from_env()).ingest_email(email)


def get_project_state(project_id: str) -> ProjectState:
    return MemoryService(SupabaseMemoryStore.from_env()).get_project_state(project_id)
