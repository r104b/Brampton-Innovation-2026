"""Read-only freshness, history and citation verification inputs."""

from typing import Literal

from pydantic import Field, model_validator

from backend.models.schemas import ContractModel, RecordId


class Citation(ContractModel):
    record_type: Literal["deliverable", "question", "decision", "review"]
    record_id: RecordId
    source_id: RecordId
    evidence_id: RecordId
    expected_status: str | None = None
    excerpt: str | None = Field(default=None, min_length=1, max_length=240)


class CitationRequest(ContractModel):
    citations: list[Citation] = Field(min_length=1, max_length=50)
    version: int | None = Field(default=None, ge=0)
    as_of: str | None = None

    @model_validator(mode="after")
    def one_history_selector(self):
        if self.version is not None and self.as_of is not None:
            raise ValueError("Choose version or as_of, not both")
        return self
