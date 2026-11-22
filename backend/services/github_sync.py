"""Publish a synthetic database snapshot as a reviewable GitHub PR."""

import base64
import hashlib
import json
import os
import unicodedata
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from backend.services.clients import Client, load_registry
from backend.services.context_generator import _SECRET, _EMAIL, render_context
from backend.models.schemas import ProjectState
from backend.services.context_router import load_routing_registry, route_context

ROOT = Path(__file__).resolve().parents[2]


def context_pr_title(client_id: str, *, version: int | None = None,
                     email_subject: str | None = None) -> str:
    """Label a snapshot by its triggering email without changing deduplication."""
    def clean(value):
        value = _SECRET.sub("[REDACTED]", value)
        value = _EMAIL.sub("[REDACTED EMAIL]", value)
        return " ".join("".join(" " if unicodedata.category(char).startswith("C") else char
                                for char in value).split())

    prefix = clean(client_id.replace("-", " ").title()) + ": "
    suffix = f" (v{version})" if version is not None else ""
    subject = clean(email_subject or "") or "Update project context"
    available = max(4, 200 - len(prefix) - len(suffix))
    if len(subject) > available:
        subject = subject[:available - 3].rstrip() + "..."
    return prefix + subject + suffix


def master_revision(revision: str | None = None) -> str:
    """Return the running master commit, with explicit/local overrides for offline use."""
    if revision:
        return revision
    return os.getenv("RENDER_GIT_COMMIT") or os.environ["MASTER_REVISION"]


class GitHubClient:
    def __init__(self, repository: str, token: str):
        self.repository = repository
        self.token = token

    def request(self, method: str, path: str, data=None):
        endpoint = f"repos/{self.repository}"
        if path:
            endpoint += f"/{path}"
        return self.api(method, endpoint, data)

    def api(self, method: str, path: str, data=None):
        request = Request(
            f"https://api.github.com/{path}",
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


def client_bundle(client: Client, state: ProjectState, *, master: str, revision: str) -> dict[str, str]:
    if state.project_id != client.project_id:
        raise PermissionError("Cannot export another client's project")
    state_json = state.model_dump_json(indent=2) + "\n"
    # Structured exports must not bypass the Markdown redaction guard.
    if _SECRET.search(state_json) or _EMAIL.search(state_json):
        raise ValueError("State contains a sensitive-looking value; curate before export")
    files = {
        "context/CURRENT_STATE.md": render_context(state, fixture=client.synthetic),
        "context/state.json": state_json,
        ".sentra/client.json": json.dumps({
            "client_id": client.client_id, "project_id": client.project_id,
            "agent_purpose": client.agent_purpose, "synthetic": client.synthetic,
        }, indent=2) + "\n",
        ".sentra/master.json": json.dumps({"repository": master, "revision": revision,
                                           "kit_version": 2}, indent=2) + "\n",
    }
    for name in ("AGENTS.md", "CLAUDE.md", "context_reader.py", "context_api.py"):
        target = name if name.endswith(".md") else "agent-kit/" + name
        files[target] = (ROOT / "agent-kit" / name).read_text(encoding="utf-8")
    if any(_SECRET.search(text) or _EMAIL.search(text) for text in files.values()):
        raise ValueError("Bundle contains a sensitive-looking value; curate before export")
    return files


def publish_bundle(api, client: Client, files: dict[str, str], *,
                   email_subject: str | None = None, snapshot_version: int | None = None) -> str | None:
    """Atomically commit one client's shared kit and state; never write master."""
    if api.repository.casefold() != client.repository.casefold():
        raise PermissionError("GitHub target does not match client registry")
    metadata = api.request("GET", "")
    if not metadata or not metadata.get("private"):
        raise PermissionError("Provision a private client repository first")
    changed_paths = []
    for path, text in sorted(files.items()):
        current = api.request("GET", f"contents/{path}?{urlencode({'ref': client.base_branch})}")
        if not current or base64.b64decode(current["content"]).decode("utf-8") != text:
            changed_paths.append(path)
    # A deployment SHA alone is metadata, not a client-context update. Avoid
    # opening a client PR just because the backend was redeployed.
    content_paths = [path for path in changed_paths if path != ".sentra/master.json"]
    if not content_paths:
        return None
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    branch = "automation/client-context-" + digest
    prs = api.request("GET", "pulls?" + urlencode({
        "state": "all", "head": f"{client.repository.split('/')[0]}:{branch}",
        "base": client.base_branch,
    }))
    if prs:
        return prs[0]["html_url"]
    base_ref = api.request("GET", "git/ref/heads/" + quote(client.base_branch, safe=""))
    if not base_ref:
        raise LookupError("Client base branch is not initialized")
    parent = base_ref["object"]["sha"]
    commit = api.request("GET", f"git/commits/{parent}")
    tree = api.request("POST", "git/trees", {
        "base_tree": commit["tree"]["sha"],
        "tree": [{"path": path, "mode": "100644", "type": "blob", "content": text}
                 for path, text in sorted(files.items())],
    })
    new_commit = api.request("POST", "git/commits", {
        "message": "Update client agent kit and sourced context", "tree": tree["sha"], "parents": [parent],
    })
    ref_path = "git/ref/heads/" + quote(branch, safe="")
    existing_ref = api.request("GET", ref_path)
    if existing_ref is None:
        api.request("POST", "git/refs", {"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]})
    # A retry may find the already-created immutable branch. Do not force-push it.
    state_paths = [path for path in content_paths
                   if path.endswith("/state.json") or path.endswith("/CURRENT_STATE.md")
                   or path == "context/CURRENT_STATE.md"]
    summary = ["Changed files compared with the base branch:"]
    summary.extend(f"- `{path}`" for path in content_paths)
    summary.append("")
    summary.append("Project context/state changed: " + ("yes" if state_paths else "no"))
    if ".sentra/master.json" in changed_paths:
        summary.append("The bundle also pins the master revision used to generate this update.")
    summary.extend([
        "",
        "Review evidence, consent questions, and conflicts. Merge only the newest state version;",
        "close stale snapshot PRs. No automatic merge.",
    ])
    pr = api.request("POST", "pulls", {
        "title": context_pr_title(client.client_id, version=snapshot_version,
                                  email_subject=email_subject), "head": branch,
        "base": client.base_branch,
        "body": "\n".join(summary),
    })
    return pr["html_url"]


def mapped_bundle(registry, project, mapping, state, revision):
    client = Client(client_id=project.customer_id, project_id=project.project_id,
                    repository=f"{mapping.owner}/{mapping.repository_name}",
                    base_branch=mapping.branch, allowed_senders=project.allowed_senders,
                    agent_purpose=project.agent_purpose)
    files = client_bundle(client, state, master=registry.master_repository, revision=revision)
    folder = str(Path(mapping.context_path).parent).replace("\\", "/")
    manifest = files.pop(".sentra/client.json")
    files[".sentra/client.json"] = json.dumps({"customer_id": project.customer_id, "synthetic": True}) + "\n"
    files[f"{folder}/client.json"] = manifest
    files[f"{folder}/state.json"] = files.pop("context/state.json")
    markdown = files.pop("context/CURRENT_STATE.md")
    files[mapping.context_path] = markdown
    return client, files


def sync_project(project_id, *, registry=None, store=None, read_state=None, api_factory=None,
                 revision=None, email_subject=None):
    from backend.database.supabase_client import SupabaseMemoryStore
    from backend.services.memory import MemoryService

    store = store or SupabaseMemoryStore.from_env()
    registry = registry or load_routing_registry(store)
    project = next((p for p in registry.projects if p.project_id == project_id), None)
    if project is None:
        raise LookupError("Unknown project")
    state = (read_state or MemoryService(store).get_project_state)(project_id)
    routing = route_context(registry, project_id, state.version)
    if routing.status != "resolved":
        return routing
    results = []
    errors = 0
    for mapping in routing.destinations:
        try:
            client, files = mapped_bundle(registry, project, mapping, state,
                                          master_revision(revision))
            api = api_factory(client) if api_factory else GitHubClient(client.repository, os.environ["CONTEXT_GITHUB_TOKEN"])
            result = publish_bundle(api, client, files, email_subject=email_subject,
                                    snapshot_version=state.version)
            store._rpc("record_sync", p_mapping=mapping.mapping_id, p_version=state.version,
                       p_status="published" if result else "unchanged")
            results.append({"mapping_id": mapping.mapping_id, "pull_request": result})
        except Exception:
            store._rpc("record_sync", p_mapping=mapping.mapping_id, p_version=state.version, p_status="failed")
            errors += 1
    if errors:
        raise RuntimeError("One or more mapped destinations failed; reconciliation will retry")
    return results


def sync_client(client: Client, *, registry=None, read_state=None, api=None, revision=None,
                email_subject=None):
    from backend.services.memory import get_project_state

    registry = registry or load_registry()
    if registry.client(client.client_id) != client:
        raise PermissionError("Client is not the registered destination")
    state = (read_state or get_project_state)(client.project_id)
    files = client_bundle(client, state, master=registry.master_repository,
                          revision=master_revision(revision))
    api = api or GitHubClient(client.repository, os.environ["CONTEXT_GITHUB_TOKEN"])
    return publish_bundle(api, client, files, email_subject=email_subject, snapshot_version=state.version)


def provision_client(client: Client, token: str) -> None:
    """Explicit onboarding only, never create a repo from an incoming email."""
    api = GitHubClient(client.repository, token)
    existing = api.request("GET", "")
    if existing:
        if not existing.get("private"):
            raise PermissionError("Existing client repository must be private")
        return
    owner, name = client.repository.split("/")
    user = api.api("GET", "user")
    endpoint = "user/repos" if user["login"].casefold() == owner.casefold() else f"orgs/{owner}/repos"
    api.api("POST", endpoint, {"name": name, "private": True, "auto_init": True,
                              "description": f"Synthetic agent build for {client.client_id}"})


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id")
    parser.add_argument("--project-id")
    parser.add_argument("--provision", action="store_true", help="Explicitly create private repositories")
    args = parser.parse_args()
    if os.getenv("REGISTRY_BACKEND", "supabase") == "supabase":
        registry = load_routing_registry()
        projects = [p for p in registry.projects if not args.project_id or p.project_id == args.project_id]
        if args.client_id:
            projects = [p for p in projects if p.customer_id == args.client_id]
        if not projects:
            raise SystemExit("No matching registered projects")
        failures = 0
        for project in projects:
            try:
                if args.provision:
                    for mapping in route_context(registry, project.project_id, 0).destinations:
                        client = Client(client_id=project.customer_id, project_id=project.project_id,
                                        repository=f"{mapping.owner}/{mapping.repository_name}",
                                        base_branch=mapping.branch, allowed_senders=project.allowed_senders,
                                        agent_purpose=project.agent_purpose)
                        provision_client(client, os.environ["CONTEXT_GITHUB_TOKEN"])
                result = sync_project(project.project_id, registry=registry)
                if hasattr(result, "status"):
                    print(f"{project.project_id}: sync blocked ({result.status})")
                    failures += 1
                else:
                    print(f"{project.project_id}: {len(result)} destination(s) reconciled")
            except Exception as error:
                print(f"{project.project_id}: sync failed ({type(error).__name__})")
                failures += 1
        if failures:
            raise SystemExit(1)
        return
    registry = load_registry()  # Explicit legacy fixture compatibility only.
    clients = [registry.client(args.client_id)] if args.client_id else registry.clients
    failures = 0
    for client in clients:
        try:
            if args.provision:
                provision_client(client, os.environ["CONTEXT_GITHUB_TOKEN"])
            result = sync_client(client, registry=registry)
            print(f"{client.client_id}: {result or 'up to date'}")
        except Exception as error:
            # Do not echo network errors, payloads, or secrets into workflow logs.
            print(f"{client.client_id}: sync failed ({type(error).__name__})")
            failures += 1
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
