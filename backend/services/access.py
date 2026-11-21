"""Project-scoped backend credentials are separate from customer/project IDs."""

import json
import os
import secrets

from fastapi import HTTPException, Request


def authorize(request: Request, project_id: str, *, review=False) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Bearer credentials required")
    grants = json.loads(os.getenv("PROJECT_ACCESS_JSON", "[]"))
    for grant in grants:
        if secrets.compare_digest(token, grant["token"]):
            if project_id not in grant["projects"] or (review and not grant.get("reviewer")):
                raise HTTPException(status_code=403, detail="Project scope denied")
            return grant.get("reviewer", "reader")
    raise HTTPException(status_code=401, detail="Invalid credentials")
