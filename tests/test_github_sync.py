import base64
import pytest

from backend.services.github_sync import publish_snapshot, context_pr_title


def test_email_subject_and_version_identify_pr():
    assert context_pr_title("maple-grove", version=3, email_subject="Demo Review Meeting Summary") == (
        "Maple Grove: Demo Review Meeting Summary (v3)"
    )


@pytest.mark.parametrize("subject", [None, "", " \r\n\t "])
def test_scheduled_or_empty_subject_has_versioned_fallback(subject):
    assert context_pr_title("maple-grove", version=3, email_subject=subject) == (
        "Maple Grove: Update project context (v3)"
    )


def test_title_redacts_sensitive_patterns_and_control_characters():
    title = context_pr_title("maple-grove", version=3,
                             email_subject="Review\r\nsecret=fictionalSecret jane@example.test\u202e update")
    assert "fictionalSecret" not in title and "jane@example.test" not in title
    assert "\n" not in title and "\r" not in title and "\u202e" not in title
    assert "[REDACTED]" in title and title.endswith("(v3)")


def test_long_subject_preserves_client_and_version():
    title = context_pr_title("maple-grove", version=123, email_subject="Meeting "*100)
    assert len(title) <= 200
    assert title.startswith("Maple Grove: Meeting") and title.endswith("... (v123)")


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
