"""Exercise Person B's memory service through Person C's export boundary offline."""

import pytest

from backend.ai.extractor import FixtureExtractor
from backend.database.supabase_client import SupabaseMemoryStore
from backend.services.context_generator import render_project_context
from backend.services.memory import MemoryService
from test_memory import FixtureStore, PROJECT, email, item


def test_default_reader_calls_memory_service_and_preserves_replayed_state(monkeypatch):
    store = FixtureStore()
    monkeypatch.setattr(SupabaseMemoryStore, "from_env", classmethod(lambda cls: store))
    first = email("context-first", "Please add SMS confirmations. Which SMS provider should be used?")
    repeat = email("context-second", "Please add SMS confirmations again.")
    memory = MemoryService(store, FixtureExtractor({
        first.source_id: [
            item(first, "deliverable", "SMS confirmations", "Send SMS after booking."),
            item(first, "question", "Which SMS provider should be used?", ""),
        ],
        repeat.source_id: [item(repeat, "deliverable", "SMS confirmations", "Send SMS after booking.")],
    }))
    memory.ingest_email(first)
    first_output = render_project_context(PROJECT, fixture=True)
    assert "State version: 1" in first_output
    assert "context\\-first" in first_output
    memory.ingest_email(repeat)
    output = render_project_context(PROJECT, fixture=True)
    state = memory.get_project_state(PROJECT)
    assert len(state.deliverables) == len(state.questions) == 1
    assert "State version: 2" in output
    assert "context\\-second" in output
    assert "Client consent required." in output
    assert "SYNTHETIC FIXTURE" in output
    assert memory.ingest_email(first).status == "already_processed"
    assert render_project_context(PROJECT, fixture=True) == output


def test_conflict_is_rendered_without_overwriting_approved_decision():
    first = email("approved-source", "Use DemoText for this demo.")
    second = email("conflict-source", "Switch to ExampleText for this demo.")
    store = FixtureStore()
    memory = MemoryService(store, FixtureExtractor({
        source.source_id: [item(source, "decision", "SMS provider", source.body)]
        for source in [first, second]
    }))
    memory.ingest_email(first)
    memory.resolve_review(PROJECT, store.snapshot["reviews"][0]["id"],
                          reviewer="synthetic-reviewer", approve=True)
    memory.ingest_email(second)
    output = render_project_context(PROJECT, read_state=memory.get_project_state, fixture=True)
    active = output.split("## Active decisions")[1].split("##")[0]
    pending = output.split("## Pending reviews and conflicts")[1]
    assert "Use DemoText" in active
    assert "ExampleText" not in active
    assert "ExampleText" in pending
    assert "proposal has not been applied" in pending


def test_unknown_project_does_not_render_empty_success():
    memory = MemoryService(FixtureStore())
    with pytest.raises(LookupError, match="Unknown project"):
        render_project_context("missing", read_state=memory.get_project_state)


def test_wrong_project_from_reader_is_rejected():
    memory = MemoryService(FixtureStore())
    with pytest.raises(PermissionError, match="different project"):
        render_project_context("another-project", read_state=lambda _: memory.get_project_state(PROJECT))
