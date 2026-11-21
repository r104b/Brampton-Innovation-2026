"""Authorized project read interfaces and explicit source-assignment review."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from backend.models.routing import ReviewAssignment
from backend.services.access import authorize
from backend.services.context_generator import render_context
from backend.services.context_router import load_routing_registry
from backend.services.identification import active_projects
from backend.services.memory import get_project_state

router = APIRouter(tags=["project context"])


def authorized_state(request, project_id):
    authorize(request, project_id)
    registry = load_routing_registry()
    if project_id not in {p.project_id for p in active_projects(registry)}:
        raise HTTPException(status_code=403, detail="Project inactive or unknown")
    try:
        return get_project_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@router.get("/projects/{project_id}/state")
def state(project_id: str, request: Request):
    return authorized_state(request, project_id)


@router.get("/projects/{project_id}/context", response_class=PlainTextResponse)
def context(project_id: str, request: Request):
    return PlainTextResponse(render_context(authorized_state(request, project_id), fixture=True),
                             media_type="text/markdown")


@router.post("/identification/{source_id}/assign")
def assign(source_id: str, payload: ReviewAssignment, request: Request, background_tasks: BackgroundTasks):
    from backend.database.supabase_client import SupabaseMemoryStore
    from backend.services.identification import assign_source
    from backend.api.gmail import sync_after_ingestion
    import os

    reviewers = [authorize(request, a.project_id, review=True) for a in payload.assignments]
    registry = load_routing_registry()
    try:
        results = assign_source(registry, SupabaseMemoryStore.from_env(), source_id,
                                payload, reviewer=reviewers[0])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Assignment scope denied") from exc
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail="Assignment or evidence is invalid") from exc
    if os.getenv("CLIENT_SYNC_ENABLED", "false").lower() == "true":
        for assignment in payload.assignments:
            background_tasks.add_task(sync_after_ingestion, assignment.project_id, registry)
    return results
