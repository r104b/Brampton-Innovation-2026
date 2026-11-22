"""Authenticated route for emails forwarded by the Gmail integration."""

import logging
import os
from email.utils import parseaddr

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool

from backend.models.schemas import IncomingEmail, IngestionResponse
from backend.models.routing import RoutingRegistry
from backend.services.ingestion import IngestionUnavailable, accept_email
from backend.services.clients import route_email

router = APIRouter(tags=["ingestion"])


def sync_after_ingestion(client, registry, *, email_subject=None):
    from backend.services.github_sync import sync_client, sync_project

    try:
        if isinstance(registry, RoutingRegistry):
            sync_project(client, registry=registry, email_subject=email_subject)
        else:
            sync_client(client, registry=registry, email_subject=email_subject)
    except Exception as error:
        logging.getLogger(__name__).warning("Client context sync failed (%s); scheduled reconciliation will retry",
                                           type(error).__name__)


@router.post("/ingest/email", response_model=IngestionResponse)
async def ingest_email(
    payload: IncomingEmail,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
) -> IngestionResponse:
    loader = getattr(request.app.state, "registry_loader", None)
    registry = await run_in_threadpool(loader) if loader else getattr(request.app.state, "client_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Client registry is not configured")
    if isinstance(registry, RoutingRegistry):
        from backend.database.supabase_client import SupabaseMemoryStore
        from backend.services.identification import ingest_identified, identify

        normalized = payload.model_copy(update={"sender": parseaddr(payload.sender)[1].casefold()})
        try:
            project_id, candidate_ids, _ = identify(registry, normalized)
            header = request.headers.get("x-sentra-client-id")
            project = next((p for p in registry.projects if p.project_id == project_id), None)
            candidate_customers = {p.customer_id for p in registry.projects if p.project_id in candidate_ids}
            if header and ((project is not None and header != project.customer_id)
                           or (project is None and candidate_customers != {header})):
                raise PermissionError("Customer header does not match project")
            result, project_id = await run_in_threadpool(
                ingest_identified, registry, normalized, SupabaseMemoryStore.from_env()
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Project access denied") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Ingestion temporarily unavailable") from exc
        if project_id and os.getenv("CLIENT_SYNC_ENABLED", "false").lower() == "true":
            background_tasks.add_task(sync_after_ingestion, project_id, registry, email_subject=payload.subject)
        response.status_code = 200 if result.status == "already_processed" else 202
        return result
    try:
        client = route_email(registry, payload)
        supplied_client = request.headers.get("x-sentra-client-id")
        if supplied_client is not None and supplied_client != client.client_id:
            raise PermissionError("Client header does not match project route")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Client route is not authorized") from exc
    try:
        normalized = payload.model_copy(update={"sender": parseaddr(payload.sender)[1].casefold()})
        result = await accept_email(normalized, request.app.state)
    except IngestionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email ingestion is not configured",
        ) from exc
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail="Project access denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Ingestion temporarily unavailable") from exc

    if os.getenv("CLIENT_SYNC_ENABLED", "false").lower() == "true":
        background_tasks.add_task(sync_after_ingestion, client, registry, email_subject=payload.subject)

    response.status_code = (
        status.HTTP_200_OK
        if result.status == "already_processed"
        else status.HTTP_202_ACCEPTED
    )
    return result
