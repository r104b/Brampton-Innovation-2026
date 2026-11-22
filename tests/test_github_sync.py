import base64

from backend.services.github_sync import publish_snapshot


def test_repository_metadata_url_has_no_trailing_slash(monkeypatch):
    from backend.services.github_sync import GitHubClient

    client = GitHubClient("team/demo", "fictional-token")
    calls = []
    monkeypatch.setattr(client, "api", lambda method, path, data: calls.append(path))
    client.request("GET", "")
    client.request("GET", "git/ref/heads/main")
    assert calls == ["repos/team/demo", "repos/team/demo/git/ref/heads/main"]


class FakeGitHub:
    repository = "team/demo"

    def __init__(self, *, content=None, prs=None):
        self.content = content
        self.prs = prs or []
        self.calls = []

    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path.startswith("contents/") and method == "GET":
            return self.content
        if path.startswith("pulls?"):
            return self.prs
        if path == "git/ref/heads/main":
            return {"object": {"sha": "base-sha"}}
        if path.startswith("git/ref/"):
            return None
        if path == "pulls":
            return {"html_url": "https://github.com/team/demo/pull/1"}
        return {}


def test_no_change_causes_no_writes():
    client = FakeGitHub(content={"content": base64.b64encode(b"snapshot").decode()})
    assert publish_snapshot(client, "snapshot") is None
    assert all(method == "GET" for method, _, _ in client.calls)


def test_replay_reuses_existing_pr_without_writes():
    client = FakeGitHub(prs=[{"html_url": "existing-pr"}])
    assert publish_snapshot(client, "snapshot") == "existing-pr"
    assert all(method == "GET" for method, _, _ in client.calls)


def test_new_content_creates_only_snapshot_commit_and_pr():
    client = FakeGitHub()
    assert publish_snapshot(client, "snapshot").endswith("/pull/1")
    writes = [(method, path, data) for method, path, data in client.calls if method != "GET"]
    assert [(method, path) for method, path, _ in writes] == [
        ("POST", "git/refs"), ("PUT", "contents/context/DATABASE_STATE.md"), ("POST", "pulls")
    ]
    assert base64.b64decode(writes[1][2]["content"]) == b"snapshot"
    assert writes[0][2]["ref"].startswith("refs/heads/automation/context-")
