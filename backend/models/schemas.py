"""Team interfaces. Coordinate contract changes through a reviewed PR."""

from typing import Annotated, Literal, Self
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmailPayload(ContractModel):
    source_id: Annotated[str, Field(min_length=1, max_length=256)]
    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    source_type: Literal["email"]
    subject: str
    sender: str
    received_at: Annotated[AwareDatetime, Field(strict=False)]
    body: Annotated[str, Field(min_length=1, max_length=100_000)]

    @field_validator("received_at", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        # FastAPI decodes JSON before validation; permit ISO strings there too.
        if not isinstance(value, (str, datetime)):
            raise ValueError("received_at must be an ISO 8601 timestamp")
        return value


class ExtractedItem(ContractModel):
    type: Literal["deliverable", "decision", "question", "concern", "qa_result"]
    title: str
    description: str
    proposed_status: str | None
    source_id: str
    source_quote: str
    requires_review: bool


class IncomingEmail(EmailPayload):
    """Existing Gmail fields; absent identity is held for identification review."""

    project_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class IngestionResponse(ContractModel):
    status: Literal["accepted", "already_processed", "requires_review"]
    source_id: str


RecordId = Annotated[str, Field(min_length=1)]
NonEmptyText = Annotated[str, Field(min_length=1)]
DeliverableStatus = Literal["open", "in_progress", "implemented", "verified", "blocked"]


class EvidenceReference(ContractModel):
    """Public citation; raw source text stays in the authorized database."""

    evidence_id: RecordId
    source_id: RecordId
    kind: Literal["requirement", "implementation", "qa_result", "client_answer", "decision"]
    excerpt: str | None = None


class StateRecord(ContractModel):
    id: RecordId
    updated_at: AwareDatetime
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]


class Deliverable(StateRecord):
    title: NonEmptyText
    description: str
    status: DeliverableStatus
    blocked_reason: NonEmptyText | None

    @model_validator(mode="after")
    def validate_status_support(self) -> Self:
        if self.status == "verified" and not any(
            ref.kind == "qa_result" for ref in self.evidence
        ):
            raise ValueError("verified deliverables require QA evidence")
        if (self.status == "blocked") != (self.blocked_reason is not None):
            raise ValueError("blocked_reason is required only for blocked deliverables")
        return self


class Question(StateRecord):
    question: NonEmptyText
    state: Literal["open", "answered"]
    requires_client_consent: bool
    answer: NonEmptyText | None
    answered_source_id: RecordId | None

    @model_validator(mode="after")
    def validate_answer(self) -> Self:
        if self.state == "open":
            if self.answer is not None or self.answered_source_id is not None:
                raise ValueError("open questions cannot contain an approved answer")
        elif self.answer is None or not any(
            ref.source_id == self.answered_source_id and ref.kind == "client_answer"
            for ref in self.evidence
        ):
            raise ValueError("answered questions require an answer and matching client evidence")
        return self


class Decision(StateRecord):
    statement: NonEmptyText
    state: Literal["active", "superseded"]
    supersedes_id: RecordId | None


class ReviewWarning(ContractModel):
    id: RecordId
    item_type: Literal["deliverable", "question", "decision"]
    item_id: RecordId
    reason: NonEmptyText
    proposed_change: NonEmptyText
    created_at: AwareDatetime
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]


class ProjectState(ContractModel):
    """One authorized, transactionally consistent project snapshot."""

    schema_version: Literal[1]
    project_id: RecordId
    project_name: NonEmptyText
    project_summary: str
    version: Annotated[int, Field(ge=0)]
    as_of: AwareDatetime
    deliverables: list[Deliverable]
    questions: list[Question]
    decisions: list[Decision]
    review_warnings: list[ReviewWarning]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        groups = {
            "deliverable": self.deliverables,
            "question": self.questions,
            "decision": self.decisions,
        }
        for records in [*groups.values(), self.review_warnings]:
            ids = [record.id for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError("record IDs must be unique within each collection")
        for warning in self.review_warnings:
            if warning.item_id not in {r.id for r in groups[warning.item_type]}:
                raise ValueError("review warning must reference an existing record")
        decisions = {decision.id: decision for decision in self.decisions}
        for decision in self.decisions:
            seen = {decision.id}
            current = decision
            while current.supersedes_id is not None:
                previous = decisions.get(current.supersedes_id)
                if previous is None or previous.id in seen:
                    raise ValueError("decision history must exist and be acyclic")
                if previous.state != "superseded":
                    raise ValueError("replaced decisions must be marked superseded")
                seen.add(previous.id)
                current = previous
        return self
