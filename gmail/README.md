# Test Gmail setup

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
