# Current facts, freshness, history and evidence

This replaces the earlier historical-retrieval deferral. The repo snapshot is a
portable cache, while the read-only backend is the source for current answers.
No second LLM summarizes or invents the retrieved state.

## Enable it

1. Apply `supabase/migrations/003_history_retrieval.sql` after 001 and 002 in the
   team's test database. Run it once. It captures existing state at installation
   time and future committed memory updates using a deferred transaction trigger.
2. Run the updated backend with its normal Supabase and master-repo environment.
   Add project read grants to secret `PROJECT_ACCESS_JSON`. For example:

```json
[{"token":"REPLACE_LOCALLY","projects":["maple-grove-demo"]}]
```

   A read grant does not need reviewer privileges. Give a different scoped
   credential to another customer; never distribute the Supabase/GitHub keys.
3. Commit/publish shared kit version 2 through the normal client context PR, then
   merge/review and update the client checkout. The new files include
   `agent-kit/context_api.py`. Existing client repos do not gain it until synced.
4. In the agent process environment set `SENTRA_API_URL` to the backend origin
   and `SENTRA_API_TOKEN` to its project read credential. Use HTTPS except for
   local loopback testing. Neither value is copied from source documents.

## Session startup

```sh
python agent-kit/context_api.py current --project-id maple-grove-demo
```

The tool selects the local project manifest and sends its cached version and
content fingerprint. The backend authorizes that project before any privileged
read, retrieves a consistent current snapshot, and returns structured state plus
Markdown. It reports `fresh`, `stale`, `unverified`, or `inconsistent`. Even when
the repo is stale, the returned database state can be used without waiting for
the PR to merge. Matching version alone does not establish freshness.

The client reader defaults to live retrieval too. Offline inspection requires
`python agent-kit/context_reader.py --offline --project-id maple-grove-demo` and
is explicitly marked unverified. Missing credentials, outage, scope mismatch,
or a redirect fail closed: no silent fallback pretending cache is current.
Retrieval responses use `Cache-Control: no-store`. This checks freshness at the
time of the read; fetch again after an update or before a new material claim.

## Historical state versus source date

```sh
python agent-kit/context_api.py history --project-id maple-grove-demo --as-of 2025-09-03T00:00:00-04:00
python agent-kit/context_api.py history --project-id maple-grove-demo --version 0
python agent-kit/context_api.py sources --project-id maple-grove-demo --start 2025-09-02T00:00:00-04:00 --end 2025-09-03T00:00:00-04:00
```

Historical state means the latest recorded committed project snapshot at or
before an explicit timezone-aware instant, or the recorded requested version.
Snapshots retain decisions, unanswered questions, status and pending reviews
together. Writes through `memory_commit` capture history in the same transaction;
failed transactions leave no history. Intermediate changes within one
transaction were not separately committed states and are not represented as
such. `observed_at` is the database capture timestamp near transaction completion,
not a claim to reconstruct the exact instant a human first learned something.

Source date means the email/meeting receipt timestamp in a half-open interval
`[start,end)`. Evidence also reports when its project association and evidence row
were recorded. A late import of a 2025 email does not create a 2025 state snapshot.
Source lookup returns up to 200 evidence rows, flags truncation, redacts common
sensitive values, and omits full bodies and sender addresses. Narrow a truncated
interval before claiming it covers all results.

History before migration capture is deliberately unavailable. Existing event
metadata cannot reliably reconstruct it. The migration never backdates today's
snapshot to its old `as_of`. Missing history, missing versions, and missing
sources require "Not enough verified information." The current date being later
than a requested date is not evidence a corresponding snapshot exists.

Direct administrative edits to product tables outside the memory service are
outside the versioned-write contract. Apply product changes through the service;
registry configuration is separate from product-state history.

## Citation validation

Save a request such as this outside tracked source, using exact IDs from the
retrieved state:

```json
{"citations":[{"record_type":"question","record_id":"Q-001","source_id":"BASELINE-001","evidence_id":"00000000-0000-4000-8000-000000000007","expected_status":"open"}]}
```

```sh
python agent-kit/context_api.py verify --project-id maple-grove-demo --citations REQUEST.json
```

The verifier checks the record's actual evidence association, project, exact
source/evidence IDs, expected status, and whether the quote is a real source
span. A verified status claim must cite QA evidence; an answered question claim
must cite its approved client-answer source. Optional `excerpt` is checked against
the returned source excerpt. Historical verification accepts top-level `version`
or `as_of`; without one it checks current state. A valid citation does not prove
that arbitrary prose logically follows from a quote. Agents must still avoid
unsupported inference and distinguish proposals from approved facts.

CLI exit codes: 0 retrieved/supported; 1 unavailable/configuration/network error;
2 no matching history/source or unsupported citations. No natural-language model
is used for these checks. Agent instructions require retrieval and verification;
an agent that ignores tool use is not guaranteed hallucination-free.

## HTTP interface

All paths are under `/api/projects/{project_id}` and require a project-scoped
bearer credential:

| Method/path | Purpose |
| --- | --- |
| `GET /agent-context?local_version=0&local_hash=...` | Current state, fingerprint, Markdown, freshness |
| `GET /history?as_of=...` or `?version=0` | Captured historical snapshot with coverage boundary |
| `GET /sources?start=...&end=...` | Date-scoped source evidence |
| `POST /citations/verify` | Read-only citation verification |

History takes exactly one selector. Dates require timezones; source intervals
must increase and be no longer than 366 days. Citation requests are limited to
50 entries. Unknown projects/scopes do not leak another customer's results.

## Validation

`tests/test_live_retrieval.py` and `tests/test_agent_live_tool.py` cover stale
versions and same-version content mismatch, preserved older decisions, absent
history, receipt/knowledge time distinction, failed citations, scoped access,
tool identity checks, outages, and credential-preserving redirect rejection.

After applying 003, run `supabase/tests/history_acceptance.sql` in the test SQL
Editor. It exercises the real commit/trigger/history/evidence RPCs inside a
transaction and rolls all test records back. Its result is separate from Python
fake-store test results. No production data or account is used.

The CI `PostgreSQL history and isolation` job applies every migration and seed
to a disposable PostgreSQL 17 service, then runs this SQL acceptance test. It
does not use any live project secrets. This job follows
[GitHub's service-container setup](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
