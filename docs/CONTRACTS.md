# Shared contracts

Deployment update: this repository is the master engine. See
[CLIENT_REPOSITORIES.md](CLIENT_REPOSITORIES.md) for the authoritative
customer-to-project-to-destination relationships held in Supabase. The original
ingestion fields remain compatible; missing project ID can be held for review.
`X-Sentra-Client-ID` can additionally identify the registered customer.
The API requires a configured registry and matching sender/project route before
calling memory. The LLM never chooses or creates a destination repository.
`IngestionResponse.status` also permits `requires_review` for durably captured
unassigned sources. See the current guide for scoped GET and review endpoints.

Baseline from section 2 of `SentraContext_Three_Person_Work_Plan.pdf`, with
ingestion response codes from section 3 of the implementation guide.
These are interface definitions, not completed endpoint implementations.
Coordinate any changes through one PR reviewed by the affected teammates.

## Shared Python models

Import from `backend.models.schemas`. All fields are required; nullable
`proposed_status` must be explicitly supplied as a string or `null`.
Unknown fields are rejected. `received_at` is an ISO 8601 timestamp with a
timezone, such as `2026-11-21T15:00:00Z`.

`EmailPayload`: `source_id`, `project_id`, `source_type` (only `email`),
`subject`, `sender`, `received_at`, `body`.

`ExtractedItem`: `type` (`deliverable`, `decision`, `question`, `concern`, or
`qa_result`), `title`, `description`, `proposed_status` (string or null),
`source_id`, `source_quote`, `requires_review` (boolean).

An extraction proposes a change; it does not authorize a database update.
Person B must validate the exact quote against the original source and apply
evidence, review, and state transition rules before persisting changes.

## HTTP interfaces

| Method and path | Input | Success response |
| --- | --- | --- |
| `POST /api/ingest/email` | JSON `EmailPayload`; `Authorization: Bearer <INGEST_TOKEN>` | `202` with `{"status":"accepted","source_id":"gmail-001"}` after durable acceptance; `200` with `{"status":"already_processed","source_id":"gmail-001"}` on replay |
| `GET /api/projects/{id}/state` | Authorized project ID | `200 application/json` with `ProjectState` |
| `GET /api/projects/{id}/context` | Authorized project ID | `200 text/markdown` rendered deterministically from authoritative state |

Invalid or missing credentials return `401`; unauthorized project access returns
`403`; invalid payloads return `422`. Person A implements authentication and
project scope checks before processing. Never return `accepted` before durable
storage succeeds. Deduplicate on `(source_type, source_id)`, including replays
that try to change the project. Do not log bodies or tokens.

`ProjectState` is now fully typed. See [the B/C state contract](PROJECT_STATE.md)
for fields, status rules, history, version semantics, and producer/consumer duties.
The complete fictional example is `sample-data/project-state.json`; the empty
example in `sample-data/contracts.json` is for validation only, not real state.

## Ownership and repository paths

This repository uses `backend/` directly; the PDFs' `backend/app/` paths map
to it. Do not create a second application tree.

| Owner | Scope |
| --- | --- |
| A | `gmail/`, `backend/main.py`, `backend/api/`, `backend/services/ingestion.py`; route names, Gmail validation, authentication; shared dependencies and environment template |
| B | `backend/ai/`, `backend/models/`, `backend/database/`, `backend/services/memory.py`, `supabase/`; extraction types, authoritative state, evidence, migrations |
| C | Context generator, GitHub sync, `context/`, `.github/`, `tests/`, `AGENTS.md`, `CLAUDE.md`; deterministic rendering and CI |

Suggested branches: `feature/gmail-api`, `feature/ai-memory`, and
`feature/context-devops`. Contract changes need coordinated review.

## Local contract check

From the repository root:

```sh
python -m pip install -r backend/requirements.txt pytest
python -m pytest tests/test_contracts.py
```

Synthetic JSON examples are in `sample-data/contracts.json`. These tests use no
Gmail, LLM, Supabase, or GitHub credentials.
