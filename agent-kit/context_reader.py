"""Portable context loader for any agent tooling; no third-party dependencies."""

import json
from pathlib import Path


def read_context(root: Path, project_id: str | None = None) -> dict:
    client = json.loads((root / ".sentra/client.json").read_text(encoding="utf-8"))
    if "project_id" not in client:
        matches = []
        for path in (root / "context").rglob("client.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest["client_id"] != client["customer_id"]:
                raise PermissionError("Project manifest belongs to another customer")
            if project_id is None or manifest["project_id"] == project_id:
                matches.append((path.parent, manifest))
        if len(matches) != 1:
            raise ValueError("Select one registered project ID explicitly")
        folder, manifest = matches[0]
        snapshot = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        if snapshot["project_id"] != manifest["project_id"]:
            raise PermissionError("Snapshot belongs to another project")
        return {"client": manifest, "state": snapshot}
    snapshot = json.loads((root / "context/state.json").read_text(encoding="utf-8"))
    if snapshot["project_id"] != client["project_id"]:
        raise PermissionError("Snapshot belongs to another client project")
    return {"client": client, "state": snapshot}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(read_context(root, args.project_id), indent=2))
