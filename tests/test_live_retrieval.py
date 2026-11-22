"""Live-read contract tests with deterministic database fixtures."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.retrieval import CitationRequest
from backend.models.schemas import ProjectState
from backend.services.retrieval import RetrievalService, fingerprint


ROOT = Path(__file__).resolve().parents[1]


def raw_state(state):
    result = state.model_dump(mode="json")
    result["reviews"] = [r | {"status": "pending"} for r in result.pop("review_warnings")]
    result["revision"] = state.version
    return result


@pytest.fixture
def snapshot():
    return ProjectState.model_validate_json((ROOT / "sample-data/project-state.json").read_text())


class ReadStore:
    def __init__(self, state):
        self.state = raw_state(state)
        self.history = []
        self.evidence = {}
        self.sources = []
        self.calls = []

    def read(self, project):
        return deepcopy(self.state) if project == self.state["project_id"] else None

    def capture(self, observed_at):
        self.history.append({"project_id": self.state["project_id"], "revision": self.state["revision"],
                             "version": self.state["version"], "observed_at": observed_at,
                             "snapshot": deepcopy(self.state)})

    def _rpc(self, operation, **args):
        self.calls.append((operation, args))
        if operation == "project_history":
            candidates = [entry for entry in self.history if entry["project_id"] == args["p_project"]]
            coverage = min((r["observed_at"] for r in candidates), default=None)
            if args.get("p_at"):
                cutoff = datetime.fromisoformat(args["p_at"])
                candidates = [entry for entry in candidates if datetime.fromisoformat(entry["observed_at"]) <= cutoff]
            if args.get("p_version") is not None:
                candidates = [entry for entry in candidates if entry["version"] == args["p_version"]]
            return {"coverage_start": coverage, "entry": deepcopy(candidates[-1]) if candidates else None}
        if operation == "project_evidence":
            return self.evidence.get((args["p_project"], args["p_evidence"]))
        if operation == "project_source_evidence":
            start, end = datetime.fromisoformat(args["p_from"]), datetime.fromisoformat(args["p_to"])
            return deepcopy([row for row in self.sources if start <= datetime.fromisoformat(row["received_at"]) < end])
        raise AssertionError(operation)


def test_stale_local_version_returns_newer_live_state(snapshot):
    result = RetrievalService(ReadStore(snapshot)).current(snapshot.project_id, local_version=6, local_hash="0"*64)
    assert result["freshness"] == "stale"
    assert result["state"]["version"] == 7
    assert result["basis"] == "live_database"
    assert result["state"]["review_warnings"][0]["id"] == "review-001"


def test_same_version_requires_matching_content(snapshot):
    service = RetrievalService(ReadStore(snapshot))
    assert service.current(snapshot.project_id, local_version=7, local_hash=fingerprint(snapshot))["freshness"] == "fresh"
    assert service.current(snapshot.project_id, local_version=7, local_hash="0"*64)["freshness"] == "stale"
    assert service.current(snapshot.project_id, local_version=7)["freshness"] == "unverified"
    assert service.current(snapshot.project_id, local_version=8, local_hash="0"*64)["freshness"] == "inconsistent"


def test_fingerprint_does_not_depend_on_record_order(snapshot):
    expected = fingerprint(snapshot)
    snapshot.deliverables.reverse()
    snapshot.deliverables[0].evidence.reverse()
    assert fingerprint(snapshot) == expected


def test_historical_cutoff_keeps_original_decision_after_new_feedback(snapshot):
    store = ReadStore(snapshot)
    store.capture("2026-11-21T15:00:00+00:00")
    store.state["version"] = store.state["revision"] = 8
    store.state["decisions"][1]["statement"] = "Later approved decision"
    store.capture("2026-11-22T15:00:00+00:00")
    service = RetrievalService(store)
    earlier = service.history(snapshot.project_id, as_of="2026-11-21T23:00:00Z")
    later = service.history(snapshot.project_id, version=8)
    assert next(d for d in earlier["state"]["decisions"] if d["id"] == "dec-current")["statement"] == "Use email and SMS confirmations."
    assert next(d for d in later["state"]["decisions"] if d["id"] == "dec-current")["statement"] == "Later approved decision"
    assert store.history[0]["snapshot"]["version"] == 7


def test_pre_capture_history_is_unknown_even_if_snapshot_as_of_is_old(snapshot):
    store = ReadStore(snapshot)
    store.capture("2026-11-22T15:00:00+00:00")
    result = RetrievalService(store).history(snapshot.project_id, as_of="2025-09-02T23:59:59-04:00")
    assert result["status"] == "unavailable" and result["state"] is None
    assert result["answer"] == "Not enough verified information."
    assert result["coverage_start"] == "2026-11-22T15:00:00+00:00"


@pytest.mark.parametrize("kwargs", [{}, {"as_of": "2025-09-02"}, {"as_of": "bad"},
                                    {"as_of": "2026-11-21T00:00:00Z", "version": 7}])
def test_invalid_history_selection(snapshot, kwargs):
    with pytest.raises(ValueError):
        RetrievalService(ReadStore(snapshot)).history(snapshot.project_id, **kwargs)


def test_source_receipt_date_is_separate_from_known_state_date(snapshot):
    store = ReadStore(snapshot)
    store.sources = [{"source_id": "late-import", "received_at": "2025-09-02T15:00:00+00:00",
                      "linked_at": "2026-11-22T15:00:00+00:00", "quote": "Fictional feedback",
                      "span_valid": True}]
    result = RetrievalService(store).sources(snapshot.project_id, "2025-09-02T00:00:00-04:00", "2025-09-03T00:00:00-04:00")
    assert result["results"][0]["source_id"] == "late-import"
    assert result["basis"] == "source_received_at"
    assert RetrievalService(store).history(snapshot.project_id, as_of="2025-09-02T23:00:00-04:00")["state"] is None


def citation_request(**updates):
    citation = {"record_type": "deliverable", "record_id": "del-booking", "source_id": "synthetic-booking",
                "evidence_id": "ev-booking", "expected_status": "implemented"} | updates
    return CitationRequest.model_validate({"citations": [citation]})


def verified_store(snapshot):
    store = ReadStore(snapshot)
    store.evidence[(snapshot.project_id, "ev-booking")] = {
        "evidence_id": "ev-booking", "source_id": "synthetic-booking", "kind": "implementation",
        "quote": "Booking form code is implemented.", "span_valid": True,
    }
    return store


def test_citation_checks_status_exact_identifiers_and_source_span(snapshot):
    service = RetrievalService(verified_store(snapshot))
    assert service.verify(snapshot.project_id, citation_request())["valid"]
    for change in [{"expected_status": "verified"}, {"record_id": "not-a-record"},
                   {"source_id": "wrong-source"}, {"evidence_id": "wrong-evidence"},
                   {"excerpt": "All QA passed"}]:
        assert not service.verify(snapshot.project_id, citation_request(**change))["valid"]


def test_hallucinated_quote_and_wrong_project_evidence_fail(snapshot):
    store = verified_store(snapshot)
    store.evidence[(snapshot.project_id, "ev-booking")]["span_valid"] = False
    assert not RetrievalService(store).verify(snapshot.project_id, citation_request())["valid"]
    store.evidence = {("other-project", "ev-booking"): {"span_valid": True}}
    assert not RetrievalService(store).verify(snapshot.project_id, citation_request())["valid"]


@pytest.mark.parametrize("path,method", [("agent-context", "get"), ("history?version=7", "get"),
    ("sources?start=2025-09-02T00:00:00Z&end=2025-09-03T00:00:00Z", "get"), ("citations/verify", "post")])
def test_all_retrieval_endpoints_deny_cross_project_before_privileged_reads(monkeypatch, path, method):
    monkeypatch.setenv("PROJECT_ACCESS_JSON", json.dumps([{"token": "reader-key", "projects": ["allowed-project"]}]))
    monkeypatch.setattr("backend.api.context.load_routing_registry", lambda: pytest.fail("Must deny before privileged reads"))
    with TestClient(app) as http:
        kwargs = {"headers": {"Authorization": "Bearer reader-key"}}
        if method == "post":
            kwargs["json"] = citation_request().model_dump()
        response = getattr(http, method)(f"/api/projects/other-project/{path}", **kwargs)
    assert response.status_code == 403


def test_backend_failure_is_not_replaced_with_a_fresh_local_claim(monkeypatch):
    monkeypatch.setattr("backend.api.context.authorized_project", lambda *args: None)
    class Offline:
        def read(self, project):
            raise RuntimeError("Unavailable")
    monkeypatch.setattr("backend.api.context.SupabaseMemoryStore.from_env", lambda: Offline())
    with TestClient(app) as http:
        response = http.get("/api/projects/demo-project/agent-context?local_version=7&local_hash="+"0"*64)
    assert response.status_code == 503


def test_successful_citation_endpoint_is_read_only_and_not_cacheable(snapshot, monkeypatch):
    monkeypatch.setattr("backend.api.context.authorized_project", lambda *args: None)
    monkeypatch.setattr("backend.api.context.SupabaseMemoryStore.from_env", lambda: verified_store(snapshot))
    with TestClient(app) as http:
        response = http.post(f"/api/projects/{snapshot.project_id}/citations/verify", json=citation_request().model_dump())
    assert response.status_code == 200 and response.json()["valid"]
    assert response.headers["cache-control"] == "no-store"


def test_requirement_evidence_cannot_verify_a_qa_status_claim(snapshot):
    store = ReadStore(snapshot)
    store.evidence[(snapshot.project_id, "ev-validation")] = {
        "source_id": "synthetic-validation", "evidence_id": "ev-validation",
        "kind": "requirement", "quote": "Require field validation", "span_valid": True,
    }
    request = CitationRequest.model_validate({"citations": [{
        "record_type": "deliverable", "record_id": "del-validation", "source_id": "synthetic-validation",
        "evidence_id": "ev-validation", "expected_status": "verified",
    }]})
    assert not RetrievalService(store).verify(snapshot.project_id, request)["valid"]


def test_no_future_history_from_fabricated_clock(snapshot):
    # Test fixture capture times are explicit; the service never falls back to
    # snapshot.as_of to manufacture a historical record.
    assert RetrievalService(ReadStore(snapshot)).history(snapshot.project_id, version=7)["state"] is None
