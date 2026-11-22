# Customer/project routing architecture

This guide supersedes the original one-project-per-client JSON registry design.
It implements the supplied Updated Architecture and Implementation Plan while
retaining separate private client repositories as the team's default layout.

## Authoritative data model

Supabase holds customers, projects, repository mappings, immutable sources,
source/project associations, evidence, current state, identification reviews,
and sync status. A customer can own many projects. A project can have multiple
active destinations, each with mapping ID, owner, repo, branch, and context path.
Two customers cannot share a client repo. Projects for the same customer can
share a repo using distinct `context/.../CURRENT_STATE.md` folders.

Customer IDs and project IDs are stable identifiers, not credentials. Existing
IDs remain unchanged; UUIDs or stable aliases work. Backend bearer credentials
and project grants control access independently.

## End-to-end behavior

1. Gmail's authorized test forwarder sends the original EmailPayload fields.
   Project ID may be omitted for identification review. Source ID remains the
   original Gmail message ID; replay never creates a second immutable source.
2. The backend validates sender/project association against the Supabase registry.
   Trusted explicit project metadata wins; a unique authorized sender association
   can resolve a missing ID. Multiple/unknown candidates are durably held for
   review. Mentions of multiple registered project IDs also trigger item review.
   Semantic AI identity suggestions are optional and not enabled in this version;
   the backend never guesses a project or a repo from free text.
3. Extraction and reconciliation remain evidence-backed. The immutable source
   can link to many projects, with separate project-scoped evidence and commits.
   An authenticated reviewer explicitly assigns extracted items to projects via
   `POST /api/identification/{source_id}/assign`. All item quotes and scopes are
   checked before any project commit. Retry completes partially committed splits
   without repeating completed project work. Nothing routes to GitHub while
   identification is unresolved. Item assignment does not bypass QA, conflict,
   or client-consent review in the memory service.
4. `context_router.py` looks up active approved destinations for a project and
   version. It returns resolved/unmapped/ambiguous/disabled/unknown explicitly.
   It never invents a path. Disabled customer/project records cannot publish.
5. Generation preserves work status, questions, answers, decision history, review
   warnings, stable IDs, citations, and available concise evidence excerpts.
   It is deterministic and makes no second LLM summarization call.
6. Local export proves destination selection first. Optional automatic sync then
   opens an atomic kit-and-context PR in each private mapped repo, with sync
   status saved separately. Background publication failure does not undo stored
   memory. Scheduled reconciliation retries and continues across projects.
7. After human merge and checkout update, any supported coding agent selects the
   project-specific manifest and snapshot. A customer repo may contain multiple
   projects, but the agent must choose one explicitly rather than mix their facts.

The runtime does not detect every semantic multi-project email automatically.
Use trusted project metadata or hold it for operator item assignment. Optional
AI-assisted candidate suggestions and richer identity clues can be added later;
low-confidence suggestions must remain review-only.

## Database setup

For a fresh team-owned test database, apply in this order:

1. `supabase/migrations/001_initial.sql`
2. `supabase/seed.sql`
3. `supabase/migrations/002_customer_routing.sql`
4. `supabase/routing_seed.sql`

For an existing database with 001 and its seed, apply only 002 and the routing
seed. Edit the fictional seed's `YOUR_TEAM` repo owner first. The seed registers
Maple Grove and Harbor as different customers/projects. Add further projects to
the same customer with unique destination folders. The SQL migration is provided
but has not been applied to a live database in this session.

Migration 002 retains the original source row as immutable. It replaces the
single-project evidence relationship with explicit source/project associations,
adds registry and review RPCs restricted to service_role, and enables RLS.
Authorization must still happen in the backend before calling privileged RPCs.

## Configuration and API

Set process variables from `.env.example`; files are not auto-loaded. Runtime
registry defaults to Supabase. Set `MASTER_REPOSITORY` and exact
`MASTER_REVISION`, plus test Supabase and Gemini credentials. `INGEST_TOKEN`
authenticates the dedicated Gmail forwarder. `CLIENT_SYNC_ENABLED=true` enables
best-effort background PR publication after ingestion or item assignment.

`PROJECT_ACCESS_JSON` is a secret JSON array of backend access grants:

```json
[{"token":"replace-locally","projects":["maple-grove-demo"],"reviewer":"operator-id"}]
```

Use separate credentials for independent callers. A credential without reviewer
identity can read its listed projects; assignment requires reviewer identity and
a grant for every assigned project. Never place actual tokens in source or
client manifests. IDs alone cannot authorize a GET or assignment request.

Supported routes:

- `POST /api/ingest/email`: 202 accepted or held for review, 200 replay;
  response remains `{status,source_id}`; review status is `requires_review`.
- `GET /api/projects/{id}/state`: scoped credential, typed ProjectState.
- `GET /api/projects/{id}/context`: same scope, `text/markdown`.
- `POST /api/identification/{source_id}/assign`: reviewer credential; body
  `{"assignments":[{"project_id":"...","items":[ExtractedItem]}]}`.
- `GET /health`: process health, not proof of database readiness.

Identification reviewers can inspect the pending review/source through the
team's authorized database tooling. No public raw-source listing is exposed.
The optional `X-Sentra-Client-ID` Gmail header identifies the customer, not a
single project; the server checks it against the candidate projects.

## Local preview and optional GitHub automation

```sh
python -m backend.services.context_export --project-id maple-grove-demo --output-root local-exports
```

Local bundles are placed under owner/repository/branch-hash and the registered
context folder. `local-exports/` is ignored. No GitHub write is made. Offline
fixtures can be supplied with both `--registry-json` and `--state-json`; those
are preview inputs only, never the production registry authority.

```sh
python -m backend.services.github_sync --project-id maple-grove-demo
python -m backend.services.github_sync
```

The second command reconciles all registered projects. Explicit onboarding with
`--provision` can create private repos; normal sync requires existing repos and
branches. Provisioning needs additional user/org repository-creation rights.
GitHub publishes only the registered project bundle, on a content-hash branch,
and opens a PR. It never auto-merges or force-pushes. Identical content reuses its
PR; close stale snapshot proposals in favor of the latest state version.

New Gmail-triggered PR titles include the client ID as a display label, the
triggering email subject, and the exported state version, for example
`Maple Grove: Demo Review Meeting Summary (v3)`. Subjects are kept to one line,
common secret/email patterns are redacted, and long titles are shortened.
Scheduled/review-triggered sync without an email subject uses a versioned
`Update project context` fallback. The title names the trigger, not every change
in a snapshot that may also contain other feedback. Content hashes still control
deduplication; retries reuse existing PRs and preserve their original titles.
This does not rename already-created PRs or generate a summary with another LLM.

Enable the master scheduled workflow with `CONTEXT_SYNC_ENABLED=true`. It needs
Actions secrets `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a
`CONTEXT_GITHUB_TOKEN` with Contents/Pull requests writes to client repos. The
workflow sets the master repo and revision from its checkout and reads routing
from Supabase. Scheduling is recovery, not an immediate queue or SLA.

Each destination gets:

```text
AGENTS.md
CLAUDE.md
.sentra/client.json             # customer identity
.sentra/master.json             # pinned shared-kit revision
agent-kit/context_reader.py
context/<optional-project-folder>/client.json
context/<optional-project-folder>/CURRENT_STATE.md
context/<optional-project-folder>/state.json
...existing client product code...
```

Shared kit v2 adds `agent-kit/context_api.py` for live retrieval and citation
validation. Configure project-scoped credentials per
[LIVE_RETRIEVAL.md](LIVE_RETRIEVAL.md), and apply migration 003 after routing setup.
Shared kit files are generated; keep custom product code elsewhere. The shared
kit supplies context recovery for coding agents, not arbitrary business-agent
runtime deployment. Original master `context/` files remain fictional test
artifacts. Historical lookup now uses actual recorded snapshots and date-scoped
evidence; it never invents states from before history capture began.

## Validation limits

Offline tests exercise customer/project relationships, mappings, ambiguous
identification, unauthorized reads, reviewed multi-project source splits,
project-local generation, replay, sync errors, and existing memory behavior.
The SQL migration, Gmail trigger, database credentials, private provisioning,
and live PR publication still require test-account validation. No production
SentraVoice system or real client data is used.

`REGISTRY_BACKEND=file` is retained only for older single-project fixture
compatibility; the Supabase registry is the current design and default.
