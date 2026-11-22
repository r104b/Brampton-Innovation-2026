"""Exercise the distributed agent tool without an external network."""

from io import BytesIO
import json
from pathlib import Path
import runpy
from urllib.error import URLError

import pytest

from backend.models.schemas import ProjectState
from backend.services.github_sync import client_bundle
from backend.services.clients import ClientRegistry
from backend.services.retrieval import fingerprint


ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "agent-kit/context_api.py"))


@pytest.fixture
def checkout(tmp_path):
    registry = ClientRegistry.model_validate_json((ROOT / "config/clients.example.json").read_text())
    client = registry.clients[0]
    data = json.loads((ROOT / "sample-data/project-state.json").read_text())
    data["project_id"] = client.project_id
    state = ProjectState.model_validate_json(json.dumps(data))
    files = client_bundle(client, state, master=registry.master_repository, revision="test-commit")
    for path, text in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path, state


class Opener:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return BytesIO(json.dumps(self.response).encode())


def test_agent_sends_local_fingerprint_and_uses_newer_server_state(checkout):
    root, state = checkout
    server = state.model_dump(mode="json") | {"version": 8}
    opener = Opener({"project_id": state.project_id, "freshness": "stale", "state": server})
    api = TOOL["ContextAPI"]("https://backend.example.test", "fictional-reader-key", opener=opener)
    response = api.current(root, state.project_id)
    assert response["state"]["version"] == 8
    assert "local_version=7" in opener.requests[0].full_url
    assert "local_hash=" + fingerprint(state) in opener.requests[0].full_url
    assert opener.requests[0].get_header("Authorization") == "Bearer fictional-reader-key"


def test_local_and_backend_fingerprints_match(checkout):
    _, state = checkout
    assert TOOL["local_fingerprint"](state.model_dump(mode="json")) == fingerprint(state)


def test_outage_does_not_return_cached_state_as_live(checkout):
    root, state = checkout
    api = TOOL["ContextAPI"]("http://127.0.0.1:8000", "fictional-reader-key", opener=Opener(error=URLError("offline")))
    with pytest.raises(RuntimeError, match="freshness is unverified"):
        api.current(root, state.project_id)


@pytest.mark.parametrize("url", ["http://remote.example.test", "https://user:secret@example.test", "https://example.test/?token=secret"])
def test_tool_rejects_insecure_or_credential_bearing_urls(url):
    with pytest.raises(ValueError):
        TOOL["ContextAPI"](url, "fictional-reader-key")


def test_wrong_project_response_cannot_cross_client_boundary(checkout):
    root, state = checkout
    api = TOOL["ContextAPI"]("https://backend.example.test", "fictional-reader-key",
                             opener=Opener({"project_id": "another-project", "state": {}}))
    with pytest.raises(PermissionError):
        api.current(root, state.project_id)


def test_redirect_is_not_allowed_to_forward_credentials():
    assert TOOL["NoRedirect"]().redirect_request(None, None, 302, "redirect", {}, "https://other.test") is None
