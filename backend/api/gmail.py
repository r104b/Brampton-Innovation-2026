"""Authenticated route for emails forwarded by the Gmail integration."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.models.schemas import EmailPayload, IngestionResponse
from backend.services.ingestion import IngestionUnavailable, accept_email

router = APIRouter(tags=["ingestion"])


@router.post("/ingest/email", response_model=IngestionResponse)
async def ingest_email(
    payload: EmailPayload,
    request: Request,
    response: Response,
) -> IngestionResponse:
    try:
        result = await accept_email(payload, request.app.state)
    except IngestionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email ingestion is not configured",
        ) from exc

    response.status_code = (
        status.HTTP_200_OK#replay
        if result.status == "already_processed"
        else status.HTTP_202_ACCEPTED
    )
    return result
