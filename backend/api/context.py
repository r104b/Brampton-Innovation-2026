"""Authorized project read interfaces and explicit source-assignment review."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from backend.models.routing import ReviewAssignment
from backend.services.access import authorize
from backend.services.context_generator import render_context
from backend.services.context_router import load_routing_registry
from backend.services.identification import active_projects
from backend.services.memory import get_project_state
from backend.database.supabase_client import SupabaseMemoryStore
from backend.models.retrieval import CitationRequest
from backend.services.retrieval import RetrievalService

router = APIRouter(tags=["project context"])


def authorized_project(request, project_id):
    authorize(request, project_id)
    registry = load_routing_registry()
    if project_id not in {p.project_id for p in active_projects(registry)}:
        raise HTTPException(status_code=403, detail="Project inactive or unknown")


def authorized_state(request, project_id):
    authorized_project(request, project_id)
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


def retrieve(http_request, project_id, operation, **kwargs):
    # Authenticate and authorize BEFORE any privileged history/evidence call.
    authorized_project(http_request, project_id)
    try:
        service = RetrievalService(SupabaseMemoryStore.from_env())
        result = getattr(service, operation)(project_id, **kwargs)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Project scope mismatch") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid retrieval input or unsafe export") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Retrieval unavailable; do not assume repository context is current") from exc


@router.get("/projects/{project_id}/agent-context")
def agent_context(project_id: str, request: Request,
                  local_version: int | None = Query(default=None, ge=0),
                  local_hash: str | None = Query(default=None, pattern="^[0-9a-f]{64}$")):
    return retrieve(request, project_id, "current", local_version=local_version, local_hash=local_hash)


@router.get("/projects/{project_id}/history")
def history(project_id: str, request: Request, as_of: str | None = None,
            version: int | None = Query(default=None, ge=0)):
    return retrieve(request, project_id, "history", as_of=as_of, version=version)


@router.get("/projects/{project_id}/sources")
def sources(project_id: str, request: Request, start: str, end: str):
    return retrieve(request, project_id, "sources", start=start, end=end)


@router.post("/projects/{project_id}/citations/verify")
def verify_citations(project_id: str, request: Request, payload: CitationRequest):
    return retrieve(request, project_id, "verify", request=payload)


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
