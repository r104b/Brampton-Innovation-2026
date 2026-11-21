"""SentraContext HTTP API."""

import hmac
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.gmail import router as gmail_router

app = FastAPI(title="SentraContext API")
app.include_router(gmail_router, prefix="/api")


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
