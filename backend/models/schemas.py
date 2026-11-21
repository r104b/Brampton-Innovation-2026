"""Team interfaces. Coordinate contract changes through a reviewed PR."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmailPayload(ContractModel):
    source_id: str
    project_id: str
    source_type: Literal["email"]
    subject: str
    sender: str
    received_at: AwareDatetime
    body: str


class ExtractedItem(ContractModel):
    type: Literal["deliverable", "decision", "question", "concern", "qa_result"]
    title: str
    description: str
    proposed_status: str | None
    source_id: str
    source_quote: str
    requires_review: bool


class IngestionResponse(ContractModel):
    status: Literal["accepted", "already_processed"]
    source_id: str


class ProjectState(ContractModel):
    """Top-level read contract; Person B defines record schemas with Person C."""

    version: int
    deliverables: list[dict[str, object]]
    questions: list[dict[str, object]]
    decisions: list[dict[str, object]]
