import json
from copy import deepcopy

import pytest

from backend.ai.extractor import FixtureExtractor
from backend.models.schemas import EmailPayload, ExtractedItem
from backend.services.memory import MemoryService


class FixtureStore:
    def __init__(self):
        self.snapshot = {
            "project_id": "maple-grove-demo", "project_name": "Maple Grove Dental",
            "project_summary": "Fictional booking app", "revision": 0, "version": 0,
            "as_of": "2026-11-17T14:00:00Z", "client_senders": ["jordan.lee@example.test"],
            "deliverables": [], "questions": [], "decisions": [], "reviews": [],
        }
        self.sources = {}
        self.evidence = []
        self.events = []

    def read(self, project_id):
        if project_id == self.snapshot["project_id"]:
            return deepcopy(self.snapshot)
        return None

    def source(self, source_type, source_id):
        return deepcopy(self.sources.get((source_type, source_id)))

    def commit(self, project_id, revision, snapshot, source, evidence, event):
        if self.snapshot["revision"] != revision:
            return "retry"
        if source is not None:
            identity = source["source_type"], source["source_id"]
            if identity in self.sources:
                if self.sources[identity]["project_id"] != project_id:
                    return "foreign_source"
                return "already_processed"
            self.sources[identity] = deepcopy(source)
        self.evidence.extend(deepcopy(evidence))
        self.events.append(deepcopy(event))
        snapshot["revision"] += 1
        snapshot["version"] += event["state_changed"]
        self.snapshot = deepcopy(snapshot)
        return "accepted"


PROJECT = "maple-grove-demo"


def email(source_id, body, sender="jordan.lee@example.test"):
    return EmailPayload.model_validate_json(json.dumps({
        "source_id": source_id, "project_id": PROJECT, "source_type": "email", "subject": "Demo",
        "sender": sender, "received_at": "2026-11-17T19:40:00Z", "body": body,
    }))


def item(source, kind, title, description, *, status=None, quote=None, review=False):
    return ExtractedItem(
        type=kind, title=title, description=description, proposed_status=status,
        source_id=source.source_id, source_quote=quote if quote is not None else source.body,
        requires_review=review,
    )


def test_overlapping_emails_add_evidence_without_duplicate_work_or_questions():
    first = email("EMAIL-002", "Please add an SMS confirmation whenever a patient successfully books "
                  "an appointment. We have not chosen an SMS provider yet.")
    second = email("EMAIL-003", "Just repeating the SMS request so it does not get missed: "
                   "patients should receive an SMS confirmation after booking.")
    question = email("EMAIL-004", "Which SMS provider should we use?")
    store = FixtureStore()
    fixture = FixtureExtractor({
        first.source_id: [
            item(first, "deliverable", "SMS confirmations", "Send an SMS after booking.",
                 quote="Please add an SMS confirmation whenever a patient successfully books an appointment."),
            item(first, "question", "Which SMS provider should be used?", "",
                 quote="We have not chosen an SMS provider yet."),
        ],
        second.source_id: [
            item(second, "deliverable", "SMS booking confirmations", "Send an SMS after booking."),
            item(second, "deliverable", "Fake verification", "", status="verified", quote="All tests passed."),
        ],
        question.source_id: [item(question, "question", question.body, "")],
    })
    calls = []

    def extract(payload):
        calls.append(payload.source_id)
        return fixture(payload)

    memory = MemoryService(store, extract)
    assert memory.ingest_email(first).status == "accepted"
    assert memory.ingest_email(first.model_copy(update={"body": "changed"})).status == "already_processed"
    assert memory.ingest_email(second).status == "accepted"
    assert memory.ingest_email(question).status == "accepted"
    state = memory.get_project_state(PROJECT)
    assert calls == ["EMAIL-002", "EMAIL-003", "EMAIL-004"]
    assert state.version == 3
    assert len(state.deliverables) == len(state.questions) == 1
    assert state.deliverables[0].status == "open"
    assert state.questions[0].state == "open"
    assert [ref.source_id for ref in state.deliverables[0].evidence] == ["EMAIL-002", "EMAIL-003"]
    assert [ref.source_id for ref in state.questions[0].evidence] == ["EMAIL-002", "EMAIL-004"]
    assert store.events[1]["invalid_items"] == 1
    for row in store.evidence:
        body = store.sources[row["source_type"], row["source_id"]]["body"]
        assert body[row["start"]:row["end"]] == row["quote"]
    assert memory.get_project_state(PROJECT) == state


def test_conflicting_feedback_requires_review_and_retains_decision_history():
    first = email("decision-1", "Use DemoText for the fictional demo.")
    conflicting = email("decision-2", "Switch the demo provider to ExampleText.")
    store = FixtureStore()
    memory = MemoryService(store, FixtureExtractor({
        source.source_id: [item(source, "decision", "SMS provider", source.body)]
        for source in [first, conflicting]
    }))
    memory.ingest_email(first)
    assert memory.get_project_state(PROJECT).version == 0
    baseline = memory.resolve_review(PROJECT, store.snapshot["reviews"][0]["id"],
                                     reviewer="demo-reviewer", approve=True)
    memory.ingest_email(conflicting)
    pending = memory.get_project_state(PROJECT)
    assert pending.decisions == baseline.decisions
    assert len(pending.review_warnings) == 1
    final = memory.resolve_review(PROJECT, pending.review_warnings[0].id,
                                  reviewer="demo-reviewer", approve=True)
    active = next(decision for decision in final.decisions if decision.state == "active")
    previous = next(decision for decision in final.decisions if decision.state == "superseded")
    assert active.supersedes_id == previous.id == baseline.decisions[0].id
    assert active.statement == conflicting.body
    assert final.review_warnings == []


def test_human_approval_requires_authorized_consent_and_passing_qa():
    sources = [
        email("initial", "Use appointment times. Which SMS provider should be used?"),
        email("progress", "The team started the time-zone display fix."),
        email("implemented", "The time-zone display fix is implemented."),
        email("qa", "The time-zone display passed five cases for this build."),
        email("unauthorized", "Use PretendText.", sender="other@example.test"),
        email("consent", "Use DemoText for the fictional demo only."),
    ]
    initial, progress, implemented, qa, unauthorized, consent = sources
    title = "Time-zone display"
    question = "Which SMS provider should be used?"
    fixtures = {
        initial.source_id: [item(initial, "deliverable", title, ""), item(initial, "question", question, "")],
        progress.source_id: [item(progress, "deliverable", title, progress.body, status="in_progress")],
        implemented.source_id: [item(implemented, "deliverable", title, implemented.body, status="implemented")],
        qa.source_id: [item(qa, "qa_result", title, qa.body, status="verified")],
        unauthorized.source_id: [item(unauthorized, "question", question, unauthorized.body, status="answered")],
        consent.source_id: [item(consent, "question", question, consent.body, status="answered")],
    }
    store = FixtureStore()
    memory = MemoryService(store, FixtureExtractor(fixtures))
    memory.ingest_email(initial)

    def submit(source):
        memory.ingest_email(source)
        return store.snapshot["reviews"][-1]["id"]

    def approve(review_id, **options):
        return memory.resolve_review(PROJECT, review_id, reviewer="demo-reviewer",
                                     approve=True, **options)

    approve(submit(progress))
    state = approve(submit(implemented))
    assert state.deliverables[0].status == "implemented"
    qa_review = submit(qa)
    with pytest.raises(ValueError, match="passing QA"):
        approve(qa_review)
    assert memory.get_project_state(PROJECT).deliverables[0].status == "implemented"
    verified = approve(qa_review, qa_passed=True).deliverables[0]
    assert verified.status == "verified"
    assert any(ref.kind == "qa_result" and ref.source_id == qa.source_id for ref in verified.evidence)

    answer_review = submit(unauthorized)
    with pytest.raises(ValueError, match="authorized client"):
        approve(answer_review)
    assert memory.get_project_state(PROJECT).questions[0].state == "open"
    memory.resolve_review(PROJECT, answer_review, reviewer="demo-reviewer", approve=False)
    answer = approve(submit(consent)).questions[0]
    assert answer.state == "answered"
    assert answer.answer == consent.body
    assert answer.answered_source_id == consent.source_id
