"""Read-only live retrieval for coding agents. Credentials stay in the environment."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_context(root, project_id):
    spec = importlib.util.spec_from_file_location("sentra_local_reader", Path(root) / "agent-kit/context_reader.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_context(Path(root), project_id)


def local_fingerprint(state):
    # Mirrors server canonicalization. Different timestamp formatting may report
    # stale conservatively; it must never turn an old snapshot into a fresh one.
    data = json.loads(json.dumps(state))
    for collection in ("deliverables", "questions", "decisions", "review_warnings"):
        data[collection].sort(key=lambda row: row["id"])
        for row in data[collection]:
            for evidence in row["evidence"]:
                evidence.setdefault("excerpt", None)
            row["evidence"].sort(key=lambda ref: (ref["source_id"], ref["evidence_id"]))
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


class ContextAPI:
    def __init__(self, base_url, credential, *, opener=None):
        parsed = urlsplit(base_url)
        loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or (parsed.scheme != "https" and not (loopback and parsed.scheme == "http"))):
            raise ValueError("Use an HTTPS backend URL, or HTTP loopback for local testing")
        if not credential:
            raise ValueError("A project-scoped API credential is required")
        self.base_url, self._credential = base_url.rstrip("/"), credential
        self.opener = opener or build_opener(NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.environ["SENTRA_API_URL"], os.environ["SENTRA_API_TOKEN"])

    def request(self, project_id, operation, *, params=None, body=None):
        url = f"{self.base_url}/api/projects/{quote(project_id, safe='')}/{operation}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, method="POST" if body is not None else "GET",
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": f"Bearer {self._credential}", "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"Live retrieval failed (HTTP {error.code}); freshness is unverified") from None
        except URLError:
            raise RuntimeError("Backend unreachable; freshness is unverified") from None
        if result.get("project_id") != project_id:
            raise PermissionError("Backend returned another project's response")
        if result.get("state") and result["state"].get("project_id") != project_id:
            raise PermissionError("Backend returned another project's state")
        return result

    def current(self, root, project_id=None):
        local = local_context(root, project_id)
        state = local["state"]
        result = self.request(local["client"]["project_id"], "agent-context", params={
            "local_version": state["version"], "local_hash": local_fingerprint(state),
        })
        if result.get("freshness") == "inconsistent":
            raise RuntimeError("Database version is older than the local snapshot; investigate the environment")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["current", "history", "sources", "verify"])
    parser.add_argument("--project-id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", help="ISO 8601 timestamp with timezone")
    parser.add_argument("--version", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--citations", type=Path, help="CitationRequest JSON file")
    args = parser.parse_args()
    try:
        api = ContextAPI.from_env()
        local = local_context(args.root, args.project_id)
        project = local["client"]["project_id"]
        if args.command == "current":
            result = api.current(args.root, project)
        elif args.command == "history":
            if (args.as_of is None) == (args.version is None):
                parser.error("History needs exactly one of --as-of or --version")
            params = {"as_of": args.as_of} if args.as_of is not None else {"version": args.version}
            result = api.request(project, "history", params=params)
        elif args.command == "sources":
            if not args.start or not args.end:
                parser.error("Sources needs --start and --end with timezones")
            result = api.request(project, "sources", params={"start": args.start, "end": args.end})
        else:
            if not args.citations:
                parser.error("Verification needs --citations JSON file")
            body = json.loads(args.citations.read_text(encoding="utf-8"))
            result = api.request(project, "citations/verify", body=body)
        print(json.dumps(result, indent=2))
        if result.get("status") in {"unavailable", "not_found"} or result.get("valid") is False:
            raise SystemExit(2)
    except (RuntimeError, ValueError, PermissionError, KeyError, OSError):
        print(json.dumps({"status": "unavailable", "freshness": "unverified",
                          "answer": "Not enough verified information.",
                          "reason": "Retrieval failed or is not configured. Do not present the local snapshot as current."}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
