"""PostgREST may return no body for successful void RPCs."""

from io import BytesIO

import pytest

from backend.database.supabase_client import SupabaseMemoryStore


@pytest.mark.parametrize("body,expected", [
    (b"", None), (b"  \n", None), (b"null", None),
    (b'{"version": 1}', {"version": 1}),
])
def test_rpc_accepts_empty_and_json_responses(monkeypatch, body, expected):
    monkeypatch.setattr("backend.database.supabase_client.urlopen",
                        lambda request, timeout: BytesIO(body))
    store = SupabaseMemoryStore("https://example.invalid", "fictional-test-key")
    assert store._rpc("record_sync") == expected
