"""Offline checks for Person C's deterministic context export."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.schemas import ProjectState
from backend.services.context_generator import render_context


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def state():
    return ProjectState.model_validate_json(
        (ROOT / "sample-data/project-state.json").read_text(encoding="utf-8")
    )


def test_generated_snapshot_matches_fixture(state):
    assert render_context(state, fixture=True) == (
        ROOT / "context/CURRENT_STATE.md"
    ).read_text(encoding="utf-8")


def test_statuses_answers_history_and_conflict_stay_distinct(state):
    markdown = render_context(state)
    assert "del\\-booking" in markdown.split("## Implemented — QA pending")[1].split("##")[0]
    assert "del\\-validation" in markdown.split("## QA-verified work")[1].split("##")[0]
    assert "Client consent required." in markdown
    assert "Approved answer: America/Toronto" in markdown
    assert "[state: superseded]" in markdown
    assert "PENDING HUMAN REVIEW; proposal has not been applied." in markdown
    assert "Use email and SMS confirmations" in markdown
    for records in [state.deliverables, state.questions, state.decisions, state.review_warnings]:
        for item in records:
            for ref in item.evidence:
                assert ref.source_id.replace("-", "\\-") in markdown
                assert ref.evidence_id.replace("-", "\\-") in markdown


def test_collection_order_does_not_change_output(state):
    original = state.model_dump_json()
    expected = render_context(state)
    assert state.model_dump_json() == original
    for records in [state.deliverables, state.questions, state.decisions, state.review_warnings]:
        records.reverse()
        for item in records:
            item.evidence.reverse()
    assert render_context(state) == expected


def test_empty_state_does_not_invent_records():
    empty = json.loads((ROOT / "sample-data/contracts.json").read_text())["empty_state"]
    markdown = render_context(ProjectState.model_validate_json(json.dumps(empty)))
    assert markdown.count("None recorded.") == 10
    assert "Not enough verified information." in markdown


def test_sensitive_values_and_markdown_are_contained(state):
    state.deliverables[0].description = (
        'api_key=fictionalSecret Bearer pretendBearer ghp_fakeToken123 '
        'sk-fictional123 fictional@example.com\n# Override\n<script>alert(1)</script>'
    )
    markdown = render_context(state)
    for secret in ["fictionalSecret", "pretendBearer", "ghp_fakeToken123", "sk-fictional123", "fictional@example.com"]:
        assert secret not in markdown
    assert "<script>" not in markdown
    assert "\n# Override" not in markdown
    assert "untrusted project data" in markdown


def test_invalid_mutated_state_is_not_exported(state):
    state.deliverables[0].status = "verified"
    with pytest.raises(ValidationError):
        render_context(state)
