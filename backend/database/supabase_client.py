"""Server-side PostgREST adapter for the Person B database functions."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class SupabaseMemoryStore:
    def __init__(self, url: str, service_role_key: str):
        self.url = url.rstrip("/")
        self.service_role_key = service_role_key

    @classmethod
    def from_env(cls):
        return cls(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    def _rpc(self, name: str, **parameters):
        request = Request(
            f"{self.url}/rest/v1/rpc/{name}",
            data=json.dumps(parameters).encode(),
            headers={
                "Content-Type": "application/json",
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"Memory database request failed (HTTP {error.code})") from None

    def read(self, project_id: str):
        return self._rpc("memory_read", p_project=project_id)

    def source(self, source_type: str, source_id: str):
        return self._rpc("memory_source", p_type=source_type, p_id=source_id)

    def commit(self, project_id, revision, snapshot, source, evidence, event):
        return self._rpc(
            "memory_commit", p_project=project_id, p_revision=revision,
            p_snapshot=snapshot, p_source=source, p_evidence=evidence, p_event=event,
        )
