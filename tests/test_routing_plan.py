"""Acceptance checks for the updated customer/project architecture."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.models.routing import RoutingRegistry, ReviewAssignment
from backend.models.schemas import IncomingEmail, ProjectState
from backend.services.context_router import route_context
from backend.services.context_export import export_project
from backend.services.github_sync import mapped_bundle, sync_project
from backend.services.identification import identify, ingest_identified, assign_source
from test_memory import FixtureStore
from test_client_repositories import FakeRepo


@pytest.fixture
def registry():
    return RoutingRegistry.model_validate({
        "master_repository": "team/master",
        "customers": [{"customer_id": "customer-a", "customer_name": "Fictional A", "status": "active"},
                      {"customer_id": "customer-b", "customer_name": "Fictional B", "status": "active"}],
        "projects": [{"project_id": name, "customer_id": customer, "project_name": name,
                      "description": "Fictional project", "status": "active",
                      "allowed_senders": [sender], "agent_purpose": "Build the fictional product"}
                     for name, customer, sender in [
                         ("project-a", "customer-a", "a@example.test"),
                         ("project-a2", "customer-a", "a@example.test"),
                         ("project-b", "customer-b", "b@example.test")]],
        "mappings": [{"mapping_id": "mapping-" + name, "project_id": name, "provider": "github",
                      "owner": "team", "repository_name": repo, "branch": "main",
                      "context_path": f"context/{name}/CURRENT_STATE.md", "active": True}
                     for name, repo in [("project-a", "client-a"), ("project-a2", "client-a"),
                                        ("project-b", "client-b")]],
    })


def incoming(project=None, *, sender="a@example.test", body="Please add booking."):
    return IncomingEmail.model_validate_json(json.dumps({
        "source_id": "source-1", "source_type": "email", "project_id": project,
        "subject": "Fictional feedback", "sender": sender,
        "received_at": "2026-11-21T15:00:00Z", "body": body,
    }))


class MultiStore:
    """RPC-shaped fake: one immutable source, many project associations."""

    def __init__(self, registry):
        self.snapshots = {}
        for project in registry.projects:
            snapshot = deepcopy(FixtureStore().snapshot)
            snapshot.update(project_id=project.project_id, project_name=project.project_name,
                            client_senders=project.allowed_senders)
            self.snapshots[project.project_id] = snapshot
        self.sources = {}
        self.links = set()
        self.reviews = {}
        self.rpc_calls = []

    def read(self, project):
        return deepcopy(self.snapshots.get(project))

    def capture(self, payload):
        data = payload.model_dump(mode="json")
        key = data["source_type"], data["source_id"]
        data["project_id"] = None
        if key in self.sources:
            assert self.sources[key] == data
        self.sources[key] = data

    def source(self, kind, source):
        return deepcopy(self.sources.get((kind, source)))

    def source_for_project(self, kind, source, project):
        if (kind, source, project) in self.links:
            return self.source(kind, source) | {"project_id": project}
        return None

    def hold(self, kind, source, candidates, reason):
        self.reviews.setdefault((kind, source), {"candidates": candidates, "reason": reason})

    def commit(self, project, revision, snapshot, source, evidence, event):
        if self.snapshots[project]["revision"] != revision:
            return "retry"
        if source:
            identity = source["source_type"], source["source_id"], project
            if identity in self.links:
                return "already_processed"
            self.links.add(identity)
        snapshot["revision"] += 1
        snapshot["version"] += event["state_changed"]
        self.snapshots[project] = deepcopy(snapshot)
        return "accepted"

    def _rpc(self, name, **kwargs):
        self.rpc_calls.append((name, kwargs))


def test_customer_can_have_multiple_projects_and_folders(registry):
    one = route_context(registry, "project-a", 3)
    two = route_context(registry, "project-a2", 4)
    assert one.status == two.status == "resolved"
    assert one.destinations[0].repository_name == two.destinations[0].repository_name
    assert one.destinations[0].context_path != two.destinations[0].context_path


def test_unmapped_disabled_and_unknown_destinations(registry):
    registry.mappings = [m for m in registry.mappings if m.project_id != "project-a"]
    assert route_context(registry, "project-a", 0).status == "unmapped"
    registry.mappings[0].active = False
    assert route_context(registry, "project-a2", 0).status == "disabled"
    assert route_context(registry, "unknown", 0).status == "unknown"


def test_ambiguous_destination_is_explicitly_blocked(registry):
    copy = registry.mappings[0].model_copy(update={"mapping_id": "duplicate"})
    registry.mappings.append(copy)
    result = route_context(registry, "project-a", 0)
    assert result.status == "ambiguous" and not result.destinations


@pytest.mark.parametrize("path", ["../CURRENT_STATE.md", "/context/CURRENT_STATE.md", "context/../../CURRENT_STATE.md", ".github/CURRENT_STATE.md"])
def test_unsafe_destinations_are_rejected(registry, path):
    data = registry.model_dump()
    data["mappings"][0]["context_path"] = path
    with pytest.raises(ValidationError):
        RoutingRegistry.model_validate(data)


def test_known_sender_and_explicit_identity(registry):
    assert identify(registry, incoming("project-a"))[0] == "project-a"
    assert identify(registry, incoming(sender="b@example.test"))[0] == "project-b"
    with pytest.raises(PermissionError):
        identify(registry, incoming("project-b"))


def test_ambiguous_source_is_saved_once_and_held_without_extraction(registry):
    store = MultiStore(registry)
    for _ in range(2):
        result, project = ingest_identified(registry, incoming(), store,
                                            extract=lambda _: pytest.fail("Must not extract ambiguously"))
        assert result.status == "requires_review" and project is None
    assert len(store.sources) == len(store.reviews) == 1
    assert not store.links


def test_multi_project_source_is_split_by_authorized_review(registry):
    source = incoming(body="project-a needs booking. project-a2 needs reminders.")
    store = MultiStore(registry)
    ingest_identified(registry, source, store)
    review = ReviewAssignment.model_validate({"assignments": [
        {"project_id": project, "items": [{"type": "deliverable", "title": title,
         "description": title, "proposed_status": "open", "source_id": source.source_id,
         "source_quote": quote, "requires_review": False}]}
        for project, title, quote in [("project-a", "Booking", "project-a needs booking."),
                                      ("project-a2", "Reminders", "project-a2 needs reminders.")]
    ]})
    results = assign_source(registry, store, source.source_id, review, reviewer="test-operator")
    assert all(result.status == "accepted" for result in results)
    assert len(store.sources) == 1 and len(store.links) == 2
    assert store.snapshots["project-a"]["deliverables"][0]["title"] == "Booking"
    assert store.snapshots["project-a2"]["deliverables"][0]["title"] == "Reminders"
    assert store.snapshots["project-b"]["deliverables"] == []
    assert all(result.status == "already_processed" for result in
               assign_source(registry, store, source.source_id, review, reviewer="test-operator"))


def test_mapped_bundle_uses_registered_path_and_records_sync_status(registry):
    project = registry.projects[0]
    fixture = json.loads((Path(__file__).resolve().parents[1] / "sample-data/contracts.json").read_text())
    state = ProjectState.model_validate_json(json.dumps(fixture["empty_state"]))
    state.project_id = project.project_id
    mapping = registry.mappings[0]
    client, files = mapped_bundle(registry, project, mapping, state, "master-commit")
    assert mapping.context_path in files
    assert "context/project-a/state.json" in files
    assert "context/CURRENT_STATE.md" not in files
    store = MultiStore(registry)
    sync_project(project.project_id, registry=registry, store=store, read_state=lambda _: state,
                 api_factory=lambda client: FakeRepo(client), revision="master-commit")
    assert store.rpc_calls[-1] == ("record_sync", {
        "p_mapping": mapping.mapping_id, "p_version": state.version, "p_status": "published"})


def test_local_exports_select_correct_customer_repository_and_project_folder(registry, tmp_path):
    fixture = json.loads((Path(__file__).resolve().parents[1] / "sample-data/contracts.json").read_text())
    for project in registry.projects:
        data = fixture["empty_state"] | {"project_id": project.project_id, "project_name": project.project_name}
        state = ProjectState.model_validate_json(json.dumps(data))
        assert export_project(registry, state, tmp_path, revision="test-master").status == "resolved"
    snapshots = list(tmp_path.rglob("state.json"))
    assert len(snapshots) == 3
    for path in snapshots:
        data = json.loads(path.read_text())
        expected_repo = "client-b" if data["project_id"] == "project-b" else "client-a"
        assert expected_repo in path.parts
        assert path.parent.name == data["project_id"]


def test_invalid_split_is_rejected_before_any_project_commit(registry):
    store = MultiStore(registry)
    source = incoming(body="project-a needs booking. project-a2 needs reminders.")
    ingest_identified(registry, source, store)
    assignment = ReviewAssignment.model_validate({"assignments": [{
        "project_id": "project-b", "items": [{"type": "deliverable", "title": "Booking",
        "description": "Booking", "proposed_status": None, "source_id": source.source_id,
        "source_quote": "project-a needs booking.", "requires_review": False}]}]})
    with pytest.raises(PermissionError):
        assign_source(registry, store, source.source_id, assignment, reviewer="operator")
    assert not store.links


def test_sync_failure_is_recorded_and_state_is_preserved(registry):
    from backend.services.memory import MemoryService

    store = MultiStore(registry)
    before = deepcopy(store.snapshots)
    class FailingRepo:
        repository = "team/client-a"

        def request(self, *args, **kwargs):
            raise RuntimeError("Simulated outage")

    with pytest.raises(RuntimeError, match="destinations failed"):
        sync_project("project-a", registry=registry, store=store,
                     read_state=MemoryService(store).get_project_state,
                     api_factory=lambda _: FailingRepo(), revision="test-master")
    assert store.snapshots == before
    assert store.rpc_calls[-1][1]["p_status"] == "failed"


def test_cross_project_read_denied_before_database_access(monkeypatch):
    monkeypatch.setenv("PROJECT_ACCESS_JSON", json.dumps([
        {"token": "test-reader", "projects": ["project-a"]}]))
    monkeypatch.setattr("backend.api.context.load_routing_registry", lambda: pytest.fail("Must deny before DB access"))
    with TestClient(app) as http:
        response = http.get("/api/projects/project-b/state", headers={"Authorization": "Bearer test-reader"})
    assert response.status_code == 403


def test_authorized_read_does_not_require_a_github_mapping(registry, monkeypatch):
    from backend.services.memory import MemoryService

    registry.mappings = []
    store = MultiStore(registry)
    monkeypatch.setenv("PROJECT_ACCESS_JSON", json.dumps([
        {"token": "test-reader", "projects": ["project-a"]}]))
    monkeypatch.setattr("backend.api.context.load_routing_registry", lambda: registry)
    monkeypatch.setattr("backend.api.context.get_project_state", MemoryService(store).get_project_state)
    with TestClient(app) as http:
        headers = {"Authorization": "Bearer test-reader"}
        response = http.get("/api/projects/project-a/state", headers=headers)
        context = http.get("/api/projects/project-a/context", headers=headers)
    assert response.status_code == context.status_code == 200
    assert response.json()["project_id"] == "project-a"
    assert context.headers["content-type"].startswith("text/markdown")
