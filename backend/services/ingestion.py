"""Service boundary between the email API and durable ingestion storage."""

from typing import Any

from backend.models.schemas import EmailPayload, IngestionResponse


class IngestionUnavailable(RuntimeError):
    """Raised when no durable email storage handler is configured."""


async def accept_email(payload: EmailPayload, app_state: Any) -> IngestionResponse:
    """Persist an email before acknowledging it to the caller.

    The configured handler must durably store new emails and deduplicate by
    (source_type, source_id), including a replay that names a different project.
    """
    handler = getattr(app_state, "email_ingestion_handler", None)
    if handler is None:
        raise IngestionUnavailable("No durable email storage handler is configured")

    result = handler(payload)
    if hasattr(result, "__await__"):
        result = await result
    if isinstance(result, IngestionResponse):
        return result
    if isinstance(result, dict):
        return IngestionResponse.model_validate(result)
    raise IngestionUnavailable("Email storage handler returned an invalid result")
