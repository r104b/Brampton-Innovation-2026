"""Controlled identification with durable review instead of silent AI assignment."""

from email.utils import parseaddr
import json

from backend.models.routing import RoutingRegistry, ReviewAssignment
from backend.models.schemas import EmailPayload, IngestionResponse
from backend.services.memory import MemoryService


def active_projects(registry: RoutingRegistry):
    customers = {c.customer_id for c in registry.customers if c.status == "active"}
    return [p for p in registry.projects if p.status == "active" and p.customer_id in customers]


def candidates_for(registry, sender):
    sender = parseaddr(sender)[1].casefold()
    return [p for p in active_projects(registry) if sender in {s.casefold() for s in p.allowed_senders}]


def identify(registry, payload):
    candidates = candidates_for(registry, payload.sender)
    explicit = payload.project_id
    if explicit and explicit not in {p.project_id for p in candidates}:
        raise PermissionError("Explicit project is unknown, disabled, or unauthorized")
    mentioned = [p for p in candidates if p.project_id in payload.body]
    if len(mentioned) > 1:
        return None, [p.project_id for p in mentioned], "Multiple projects require item-level assignment"
    if explicit:
        return explicit, [explicit], "Trusted explicit project"
    if len(candidates) == 1:
        return candidates[0].project_id, [candidates[0].project_id], "Validated sender association"
    return None, [p.project_id for p in candidates], "Ambiguous or unknown project; human review required"


def ingest_identified(registry, payload, store, *, extract=None):
    project_id, candidates, reason = identify(registry, payload)
    store.capture(payload)
    if project_id is None:
        store.hold(payload.source_type, payload.source_id, candidates, reason)
        return IngestionResponse(status="requires_review", source_id=payload.source_id), None
    data = payload.model_dump()
    data["project_id"] = project_id
    email = EmailPayload.model_validate(data)
    result = MemoryService(store, extract).ingest_email(email)
    return result, project_id


def assign_source(registry, store, source_id: str, review: ReviewAssignment, *, reviewer: str):
    """Authenticated operator explicitly splits items; all quotes checked first.

    Per-project commits are replay-safe. Review is resolved only after every
    project succeeds, so a partial failure can be retried with the same request.
    """
    if not reviewer.strip():
        raise PermissionError("Authenticated reviewer is required")
    source = store.source("email", source_id)
    if source is None:
        raise LookupError("Unknown source")
    projects = {p.project_id for p in candidates_for(registry, source["sender"])}
    if len({a.project_id for a in review.assignments}) != len(review.assignments):
        raise ValueError("Group all items for a project into one assignment")
    for assignment in review.assignments:
        if assignment.project_id not in projects:
            raise PermissionError("Assignment is outside the sender's authorized projects")
        for item in assignment.items:
            if item.source_id != source_id or not item.source_quote.strip() or item.source_quote not in source["body"]:
                raise ValueError("Assigned item lacks an exact source span")
    memory = MemoryService(store)
    results = []
    for assignment in review.assignments:
        email = EmailPayload.model_validate_json(json.dumps(source | {"project_id": assignment.project_id}))
        results.append(memory.ingest_email(email, approved_items=assignment.items))
    store._rpc("resolve_identification", p_type="email", p_id=source_id, p_reviewer=reviewer)
    return results
