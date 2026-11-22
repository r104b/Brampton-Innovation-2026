# Test Gmail setup

## Deploy the backend on Render

The repository includes a `render.yaml` Blueprint for the FastAPI web service.
In Render, create a Blueprint Instance from this GitHub repository, then add
the requested environment values in the service dashboard. Keep credentials in
Render's environment settings; do not commit them or put them in Apps Script
source. The backend needs a test Supabase project with the migrations and routing
seed applied, a Gemini API key/model, and the exact master repository name.

After the first deploy, check the service logs and open `https://<service>.onrender.com/health`.
Use `https://<service>.onrender.com/api/ingest/email` as `INGEST_URL` below.
`/health` only confirms that the process responds; it does not check Supabase or
Gmail readiness. Leave `CLIENT_SYNC_ENABLED` false for the initial connection.
The Gmail trigger and live database path still need test-account validation.

To publish generated context as client-repository pull requests, first confirm
each active Supabase mapping points to an existing private repository and base
branch. Then set `CLIENT_SYNC_ENABLED=true` in the Render service and provide
`CONTEXT_GITHUB_TOKEN` with repository Contents and Pull requests read/write
permissions, plus `MASTER_REVISION` set to the exact master commit running on
Render. The sync opens or reuses a reviewable pull request; it never merges it.
Keep publishing disabled until those destinations and credentials are ready.

Create Apps Script from `Code.gs` in a dedicated test mailbox. Configure Script
Properties `INGEST_URL` (HTTPS backend `/api/ingest/email`), `INGEST_TOKEN`, and
`CLIENT_ROUTES_JSON`, for example `{"maple-grove":"maple-grove-demo"}`.

Create the parent label `SentraContext` and nested `SentraContext/maple-grove`.
Apply both to a fictional client thread. Apply exactly one client label per
thread. Labels and project mappings must agree with the server's trusted client
registry; sender addresses must be allowlisted there. The bearer authenticates
the dedicated inbox forwarder, not individual email authors. Mail sender headers
can be spoofed: do not treat these filters as production email authentication.

Run `pollClientEmails` manually, approve Google permissions, then run
`installTrigger` for five-minute polling. Messages are sent individually, even
within the same thread. Replays are harmless through the durable source ledger.
Non-2xx messages stay eligible for the next run. Do not remove the client label
to mark a thread processed; new messages would otherwise be missed.

The demo polls the first 100 matching threads in a 30-day window. It is not an
unbounded historical mailbox importer; add pagination/cursors for larger inboxes.
Cloud Apps Script cannot reach localhost: use the team's HTTPS test deployment.
Forward meeting write-ups through the same labeled fictional email route.
