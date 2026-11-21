"""Trusted routing configuration. Email/LLM content never selects a repository."""

import json
import os
from email.utils import parseaddr
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from backend.models.schemas import ContractModel, EmailPayload


class Client(ContractModel):
    client_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{1,63}$")
    project_id: str = Field(min_length=1)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_branch: str = "main"
    allowed_senders: list[str] = Field(min_length=1)
    agent_purpose: str = Field(min_length=1)
    synthetic: Literal[True] = True


class ClientRegistry(ContractModel):
    master_repository: str
    clients: list[Client]

    @model_validator(mode="after")
    def isolation(self) -> Self:
        for key in ("client_id", "project_id", "repository"):
            values = [getattr(client, key).casefold() for client in self.clients]
            if len(values) != len(set(values)):
                raise ValueError(f"Each client must have a unique {key}")
        if any(c.repository.casefold() == self.master_repository.casefold() for c in self.clients):
            raise ValueError("Client context cannot be published to the master repository")
        return self

    def client(self, client_id: str) -> Client:
        for client in self.clients:
            if client.client_id == client_id:
                return client
        raise LookupError("Unknown client")


def load_registry() -> ClientRegistry:
    return ClientRegistry.model_validate_json(Path(os.environ["CLIENT_REGISTRY_PATH"]).read_text(encoding="utf-8"))


def route_email(registry: ClientRegistry, payload: EmailPayload) -> Client:
    candidates = [client for client in registry.clients if client.project_id == payload.project_id]
    if len(candidates) != 1:
        raise PermissionError("Unknown or ambiguous project route")
    client = candidates[0]
    sender = parseaddr(payload.sender)[1].casefold()
    if sender not in {value.casefold() for value in client.allowed_senders}:
        raise PermissionError("Sender is not authorized for this client")
    return client


def registry_json(registry: ClientRegistry) -> str:
    return json.dumps(registry.model_dump(), indent=2) + "\n"
