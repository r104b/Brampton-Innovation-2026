"""Preview validated mapped bundles locally before enabling GitHub publication."""

import argparse
import hashlib
import os
from pathlib import Path

from backend.models.routing import RoutingRegistry
from backend.models.schemas import ProjectState
from backend.services.context_router import load_routing_registry, route_context
from backend.services.github_sync import mapped_bundle, master_revision
from backend.services.memory import get_project_state


def export_project(registry, state, root, *, revision):
    routing = route_context(registry, state.project_id, state.version)
    if routing.status != "resolved":
        return routing
    project = next(p for p in registry.projects if p.project_id == state.project_id)
    for mapping in routing.destinations:
        _, files = mapped_bundle(registry, project, mapping, state, revision)
        branch_id = hashlib.sha256(mapping.branch.encode()).hexdigest()[:12]
        destination = Path(root) / mapping.owner / mapping.repository_name / branch_id
        for path, text in files.items():
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
    return routing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--registry-json", type=Path, help="Offline routing fixture only")
    parser.add_argument("--state-json", type=Path, help="Offline ProjectState fixture only")
    args = parser.parse_args()
    if bool(args.registry_json) != bool(args.state_json):
        parser.error("Supply both offline fixture files, or neither")
    if args.registry_json:
        registry = RoutingRegistry.model_validate_json(args.registry_json.read_text(encoding="utf-8"))
        state = ProjectState.model_validate_json(args.state_json.read_text(encoding="utf-8"))
        revision = "offline-fixture"
    else:
        registry, state = load_routing_registry(), get_project_state(args.project_id)
        revision = master_revision()
    if state.project_id != args.project_id:
        raise PermissionError("Snapshot does not match requested project")
    routing = export_project(registry, state, args.output_root, revision=revision)
    print(routing.model_dump_json(indent=2))
    if routing.status != "resolved":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
