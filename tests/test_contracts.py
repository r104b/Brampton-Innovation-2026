"""Offline handshake checks for the shared team interfaces."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    EmailPayload,
    ExtractedItem,
    IngestionResponse,
    ProjectState,
)


FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "sample-data/contracts.json").read_text()
)


def test_shared_examples_round_trip():
    for key, model in [
        ("email", EmailPayload),
        ("extracted_item", ExtractedItem),
        ("accepted", IngestionResponse),
        ("replayed", IngestionResponse),
        ("empty_state", ProjectState),
    ]:
        parsed = model.model_validate_json(json.dumps(FIXTURE[key]))
        assert model.model_validate_json(parsed.model_dump_json()) == parsed
    assert FIXTURE["extracted_item"]["source_id"] == FIXTURE["email"]["source_id"]
    assert FIXTURE["extracted_item"]["source_quote"] in FIXTURE["email"]["body"]


@pytest.mark.parametrize(
    "changes",
    [
        {"source_type": "meeting"},
        {"received_at": "not-a-date"},
        {"received_at": "2026-11-21T15:00:00"},
        {"project_id": 42},
        {"unexpected": "field"},
    ],
)
def test_invalid_email_contract(changes):
    with pytest.raises(ValidationError):
        EmailPayload.model_validate_json(json.dumps(FIXTURE["email"] | changes))


def test_extraction_requires_explicit_nullable_status():
    item = FIXTURE["extracted_item"] | {"proposed_status": None}
    assert ExtractedItem.model_validate(item).proposed_status is None
    del item["proposed_status"]
    with pytest.raises(ValidationError):
        ExtractedItem.model_validate(item)


@pytest.mark.parametrize("changes", [{"type": "summary"}, {"requires_review": "false"}])
def test_invalid_extraction_contract(changes):
    with pytest.raises(ValidationError):
        ExtractedItem.model_validate(FIXTURE["extracted_item"] | changes)
