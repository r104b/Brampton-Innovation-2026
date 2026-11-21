"""Publish a synthetic database snapshot as a reviewable GitHub PR."""

import base64
import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from backend.services.context_generator import render_project_context


class GitHubClient:
    def __init__(self, repository: str, token: str):
        self.repository = repository
        self.token = token

    def request(self, method: str, path: str, data=None):
        request = Request(
            f"https://api.github.com/repos/{self.repository}/{path}",
            method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and method == "GET":
                return None
            raise RuntimeError(f"GitHub sync failed (HTTP {error.code})") from None


def publish_snapshot(client, markdown: str, *, base: str = "main") -> str | None:
    """One immutable branch per content hash; replays reuse its PR.

    Only the generated database snapshot is written. No merge is performed.
    """
    path = "context/DATABASE_STATE.md"
    encoded = base64.b64encode(markdown.encode("utf-8")).decode("ascii")
    existing = client.request("GET", f"contents/{path}?{urlencode({'ref': base})}")
    if existing and base64.b64decode(existing["content"]).decode("utf-8") == markdown:
        return None
    branch = "automation/context-" + hashlib.sha256(markdown.encode()).hexdigest()[:24]
    prs = client.request("GET", "pulls?" + urlencode({
        "state": "all", "head": f"{client.repository.split('/')[0]}:{branch}", "base": base,
    }))
    if prs:
        # A closed PR is a human disposition; do not silently reopen it.
        return prs[0]["html_url"]
    ref_path = "git/ref/heads/" + quote(branch, safe="")
    if client.request("GET", ref_path) is None:
        base_ref = client.request("GET", "git/ref/heads/" + quote(base, safe=""))
        if base_ref is None:
            raise LookupError("GitHub base branch not found")
        client.request("POST", "git/refs", {
            "ref": f"refs/heads/{branch}", "sha": base_ref["object"]["sha"],
        })
    current = client.request("GET", f"contents/{path}?{urlencode({'ref': branch})}")
    if not current or base64.b64decode(current["content"]).decode("utf-8") != markdown:
        update = {"message": "Update synthetic database context", "content": encoded, "branch": branch}
        if current:
            update["sha"] = current["sha"]
        client.request("PUT", f"contents/{path}", update)
    pr = client.request("POST", "pulls", {
        "title": "Update synthetic database context",
        "head": branch, "base": base,
        "body": "Generated from the synthetic Supabase project. Review statuses, citations, "
                "and pending conflicts before merging. Supersede older snapshot PRs with "
                "the latest version; do not merge stale snapshots. No automatic merge.",
    })
    return pr["html_url"]


def main() -> None:
    markdown = render_project_context(os.environ["CONTEXT_PROJECT_ID"], fixture=True)
    client = GitHubClient(os.environ["GITHUB_REPOSITORY"], os.environ["CONTEXT_GITHUB_TOKEN"])
    result = publish_snapshot(client, markdown, base=os.getenv("CONTEXT_BASE_BRANCH", "main"))
    print(result or "Snapshot already matches the base branch.")


if __name__ == "__main__":
    main()
