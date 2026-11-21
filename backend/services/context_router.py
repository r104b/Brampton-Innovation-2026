"""Resolve only approved database mappings. Identifiers are not authorization."""

import os

from backend.database.supabase_client import SupabaseMemoryStore
from backend.models.routing import RoutingRegistry, RoutingResult


def load_routing_registry(store=None) -> RoutingRegistry:
    store = store or SupabaseMemoryStore.from_env()
    data = store._rpc("context_registry", p_master=os.environ["MASTER_REPOSITORY"])
    return RoutingRegistry.model_validate(data)


def route_context(registry: RoutingRegistry, project_id: str, version: int) -> RoutingResult:
    """Call after authorizing access to this project; no arbitrary destination input."""
    status = "resolved"
    project = next((p for p in registry.projects if p.project_id == project_id), None)
    destinations = []
    if project is None:
        status = "unknown"
    elif project.status != "active" or not any(
        c.customer_id == project.customer_id and c.status == "active" for c in registry.customers
    ):
        status = "disabled"
    else:
        mappings = [m for m in registry.mappings if m.project_id == project_id]
        destinations = [m for m in mappings if m.active]
        if not destinations:
            status = "disabled" if mappings else "unmapped"
        elif len({(m.owner.casefold(), m.repository_name.casefold(), m.branch, m.context_path)
                  for m in destinations}) != len(destinations):
            status, destinations = "ambiguous", []
    return RoutingResult(project_id=project_id, snapshot_version=version,
                         status=status, destinations=destinations)
