"""SentraContext HTTP API."""

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.gmail import router as gmail_router
from backend.api.context import router as context_router

@asynccontextmanager
async def lifespan(app):
    if os.getenv("SUPABASE_URL") and os.getenv("MASTER_REPOSITORY"):
        from backend.services.context_router import load_routing_registry

        app.state.registry_loader = load_routing_registry
    elif os.getenv("REGISTRY_BACKEND") == "file" and os.getenv("CLIENT_REGISTRY_PATH"):
        from backend.services.clients import load_registry
        from backend.services.memory import ingest_email

        app.state.client_registry = load_registry()
        app.state.email_ingestion_handler = ingest_email
    yield


app = FastAPI(title="SentraContext master API", lifespan=lifespan)
app.include_router(gmail_router, prefix="/api")
app.include_router(context_router, prefix="/api")


@app.middleware("http")
async def authenticate_email_ingestion(request, call_next):
    if request.method == "POST" and request.url.path == "/api/ingest/email":
        expected = os.getenv("INGEST_TOKEN", "")
        scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
        if (
            not expected
            or scheme.lower() != "bearer"
            or not supplied.strip()
            or not hmac.compare_digest(supplied.strip(), expected)
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}
