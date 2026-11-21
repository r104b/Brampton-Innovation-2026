"""B/C handshake checks; no external services or fabricated approvals."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.schemas import ProjectState


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "sample-data/project-state.json"


@pytest.fixture
def state():
    return json.loads(FIXTURE_PATH.read_text())


def validate(state):
    return ProjectState.model_validate_json(json.dumps(state))


def test_complete_handshake_fixture(state):
    snapshot = validate(state)
    assert {item.status for item in snapshot.deliverables} == {
        "open", "in_progress", "implemented", "verified", "blocked"
    }
    assert snapshot.questions[0].requires_client_consent
    assert snapshot.questions[0].answer is None
    assert snapshot.decisions[1].supersedes_id == snapshot.decisions[0].id
    assert snapshot.decisions[1].state == "active"
    assert snapshot.review_warnings[0].item_id == snapshot.decisions[1].id
    assert ProjectState.model_validate_json(snapshot.model_dump_json()) == snapshot


@pytest.mark.parametrize(
    "field,value",
    [("schema_version", 2), ("version", -1), ("version", "7"),
     ("as_of", "2026-11-21T15:00:00"), ("project_id", "")],
)
def test_invalid_envelope(state, field, value):
    state[field] = value
    with pytest.raises(ValidationError):
        validate(state)


@pytest.mark.parametrize(
    "index,changes",
    [(0, {"status": "done"}), (0, {"status": "verified"}),
     (0, {"blocked_reason": "Unexpected reason"}),
     (4, {"blocked_reason": None}), (0, {"evidence": []})],
)
def test_invalid_deliverable(state, index, changes):
    state["deliverables"][index].update(changes)
    with pytest.raises(ValidationError):
        validate(state)


@pytest.mark.parametrize(
    "index,changes",
    [(0, {"answer": "Unapproved answer"}), (0, {"state": "answered"}),
     (1, {"answered_source_id": "unrelated-source"}),
     (1, {"answer": None})],
)
def test_invalid_answer(state, index, changes):
    state["questions"][index].update(changes)
    with pytest.raises(ValidationError):
        validate(state)


def test_answer_requires_client_answer_evidence(state):
    state["questions"][1]["evidence"][0]["kind"] = "requirement"
    with pytest.raises(ValidationError):
        validate(state)


@pytest.mark.parametrize("collection", ["deliverables", "questions", "decisions", "review_warnings"])
def test_duplicate_ids_rejected(state, collection):
    state[collection].append(copy.deepcopy(state[collection][0]))
    with pytest.raises(ValidationError):
        validate(state)


def test_review_target_must_exist(state):
    state["review_warnings"][0]["item_id"] = "missing-decision"
    with pytest.raises(ValidationError):
        validate(state)


@pytest.mark.parametrize("predecessor", ["missing", "dec-current"])
def test_broken_decision_history(state, predecessor):
    state["decisions"][1]["supersedes_id"] = predecessor
    with pytest.raises(ValidationError):
        validate(state)


def test_replaced_decision_must_be_superseded(state):
    state["decisions"][0]["state"] = "active"
    with pytest.raises(ValidationError):
        validate(state)


def test_multi_record_decision_cycle(state):
    state["decisions"][1]["state"] = "superseded"
    state["decisions"][0]["supersedes_id"] = "dec-current"
    with pytest.raises(ValidationError):
        validate(state)


def test_raw_source_fields_rejected(state):
    state["deliverables"][0]["evidence"][0]["body"] = "untrusted source content"
    with pytest.raises(ValidationError):
        validate(state)
