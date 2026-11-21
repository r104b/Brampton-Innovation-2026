# Database-to-context handoff

## Automatic generation and PR setup

`.github/workflows/context-sync.yml` checks the synthetic database every 15
minutes and supports manual dispatch. It runs independently of email ingestion;
an email-triggered export hook is not wired into Person A's service. Scheduled
runs require the workflow on the default branch and can be delayed by GitHub.

Configure repository Actions secrets `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, and `CONTEXT_GITHUB_TOKEN`. The GitHub secret should
be a repository-scoped token with Contents and Pull requests read/write access.
A separate token also permits the PR to trigger the ordinary CI workflow.
Set repository variable `CONTEXT_PROJECT_ID` to `maple-grove-demo`, then set
`CONTEXT_SYNC_ENABLED` to `true` to enable the job. These settings have not been
configured by adding the workflow. No live PR creation has been tested yet.

The sync service reads approved state, renders it with a synthetic label, and
commits only `context/DATABASE_STATE.md` to a content-hash branch. It opens a PR;
the same content reuses its existing PR, including a closed PR, rather than
silently reopening a human disposition. Unchanged base-branch content creates
nothing. Failures are reported by the workflow and retried on the next run;
the sync does not change ingestion acknowledgements or database state.

Each distinct snapshot can have its own PR. Review the state version and close
older snapshot PRs in favor of the latest; never merge an older version after a
newer one. The service does not force-push, edit other branches, or auto-merge.
An agent on the default branch sees the exported state after human merge and
after its local checkout is updated. `AGENTS.md` points to the database export
when present. The original `CURRENT_STATE.md` remains the offline test fixture.

This provides current-state synchronization, not historical date queries.
For a question about September 2, 2025, Person B must expose authorized lookup
of original dated sources/evidence, or reconstruction of state as of a timestamp
from retained events. Source receipt time and database commit time answer
different questions. The current snapshot cannot establish either history by
itself. Git history records merged exports only, not every database event.

Person B's synchronous `backend.services.memory.get_project_state(project_id)`
now returns the shared `ProjectState`. Person C's
`render_project_context(project_id)` calls that reader and renders its result.
It rejects a result belonging to a different project and propagates missing
project or database errors instead of generating a misleading empty snapshot.

The caller must authorize project access before calling this function.
Person A owns HTTP authentication, routing, and wiring. No new public endpoint
or authentication behavior is introduced by the generator.

## Read the synthetic Supabase project

Person B must first apply the migration and seed to the team test database.
Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your terminal environment
using the team's credentials; do not place their values in committed files or
paste them into chat. The generator does not automatically load `.env` files.
The database read does not need a Gemini key or invoke an LLM.

From the repository root:

```sh
python -m backend.services.context_generator --project-id maple-grove-demo --output context/DATABASE_STATE.md --fixture
```

Keep `--fixture` for this synthetic demo database, even though storage is real.
Use a separate destination so the checked-in fixture snapshot and its manual
test remain reproducible. Review the generated file before committing it.
The command retrieves approved state; it does not ingest email or approve review
proposals. A failed read does not overwrite the output file.

For the authorized context API, Person A can return
`render_project_context(authorized_project_id)` as `text/markdown`, with
`fixture=True` for demo data. Call it from a synchronous route or a thread pool
because the Supabase reader is synchronous. Translate lookup/database errors to
appropriate HTTP responses without exposing credentials or source content.

## What has been tested

`tests/test_context_memory_integration.py` connects the actual memory service,
its project-state projection, and the renderer using Person B's in-memory test
store and deterministic extraction. It covers repeated email, overlapping work,
unanswered consent, pending conflicting decisions, unknown projects, and a
wrong-project reader result. No external credentials or live requests are used.

```sh
python -m pytest tests/test_context_memory_integration.py -q -p no:cacheprovider
```

Live Supabase and Gmail-to-context verification remain separate acceptance
checks. After a database export, run a fresh-agent read-only check against
`context/DATABASE_STATE.md` and compare it with that database's expected state;
the version-7 manual checklist belongs only to `context/CURRENT_STATE.md`.
