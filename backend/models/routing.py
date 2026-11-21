"""Customer, project and destination contracts shared by all workstreams."""

from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, model_validator

from backend.models.schemas import ContractModel, ExtractedItem


class Customer(ContractModel):
    customer_id: str
    customer_name: str
    status: Literal["active", "disabled"]


class RegisteredProject(ContractModel):
    project_id: str
    customer_id: str
    project_name: str
    description: str
    status: Literal["active", "disabled"]
    allowed_senders: list[str]
    agent_purpose: str


class RepositoryMapping(ContractModel):
    mapping_id: str
    project_id: str
    provider: Literal["github"]
    owner: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    repository_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    branch: str = Field(min_length=1)
    context_path: str
    active: bool

    @model_validator(mode="after")
    def safe_path(self) -> Self:
        path = PurePosixPath(self.context_path)
        if (not path.parts or path.is_absolute() or path.parts[0] != "context" or ".." in path.parts or "\\" in self.context_path
                or ":" in self.context_path or str(path) != self.context_path
                or path.name != "CURRENT_STATE.md" or len(path.parts) < 2
                or any(part.startswith(".") for part in path.parts)):
                raise ValueError("Context path must be context/.../CURRENT_STATE.md")
        return self


class RoutingRegistry(ContractModel):
    master_repository: str
    customers: list[Customer]
    projects: list[RegisteredProject]
    mappings: list[RepositoryMapping]

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        for records, key in [(self.customers, "customer_id"), (self.projects, "project_id"),
                             (self.mappings, "mapping_id")]:
            ids = [getattr(record, key) for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate registry identity")
        customers = {c.customer_id for c in self.customers}
        projects = {p.project_id: p for p in self.projects}
        if any(p.customer_id not in customers for p in self.projects):
            raise ValueError("Project customer does not exist")
        owners = {}
        paths = {}
        for mapping in self.mappings:
            if mapping.project_id not in projects:
                raise ValueError("Mapping project does not exist")
            repo = f"{mapping.owner}/{mapping.repository_name}".casefold()
            if repo == self.master_repository.casefold():
                raise ValueError("Master repository cannot receive client context")
            customer = projects[mapping.project_id].customer_id
            if repo in owners and owners[repo] != customer:
                raise ValueError("Different customers cannot share a repository")
            owners[repo] = customer
            destination = (repo, mapping.branch, mapping.context_path)
            if mapping.active and destination in paths and paths[destination] != mapping.project_id:
                raise ValueError("Ambiguous active destination")
            paths[destination] = mapping.project_id
        return self


class RoutingResult(ContractModel):
    project_id: str
    snapshot_version: int = Field(ge=0)
    status: Literal["resolved", "unmapped", "ambiguous", "disabled", "unknown"]
    destinations: list[RepositoryMapping]


class Assignment(ContractModel):
    project_id: str
    items: list[ExtractedItem] = Field(min_length=1)


class ReviewAssignment(ContractModel):
    assignments: list[Assignment] = Field(min_length=1)
