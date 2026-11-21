# Updated-plan alignment

Reference reviewed: `SentraContext_Updated_Architecture_and_Implementation_Plan.docx`
supplied by the user. This table separates implemented code from external setup
and optional extensions. The document's suggested ownership is planning context;
the user's broader architecture-change request authorizes the integration edits.

| Plan area | Implementation |
| --- | --- |
| Preserve existing stack | Existing Gmail payload, FastAPI, extractor, reconciliation, memory and renderer retained |
| Supabase authoritative registry | Migration 002 adds customers, project relationship/status, repository mappings and service-only registry RPC |
| Many projects/destinations | Typed registry supports multiple projects per customer and mappings per project; separate private customer repos remain default |
| Controlled identification | Explicit project plus sender validation; unique authorized sender fallback; missing/ambiguous identity saved to identification review |
| Multi-project source | One immutable source plus source/project links; authenticated operator splits extracted items with exact quote validation and replay-safe per-project commits |
| Context router | Explicit resolved/unmapped/ambiguous/disabled/unknown result; approved owner/repo/branch/context path only |
| Context content | Project/version/time, statuses, questions/answers, decision history, review warnings, IDs, citations and optional concise evidence excerpts |
| API | Existing POST fields retained, missing project ID supported for review; scoped state/context GET endpoints and item-assignment review endpoint added |
| Local-first proof | `context_export.py` generates mapped bundles without GitHub writes; tests verify separate project folders/repos |
| Optional PR automation | Publisher uses registered destinations; background attempt plus scheduled reconciliation; failed sync status retained separately |
| Fresh-agent entry point | Shared kit selects a project manifest/snapshot, checks customer/project identity, preserves consent/QA distinctions |
| Fictional test data | Routing seed registers two fictional customers/projects; original sample-memory behavior and tests retained |

Optional AI-assisted identity suggestions are not enabled. Explicit IDs and sender
associations provide the MVP identity path; semantic ambiguity needs operator
review. Automatic semantic detection/splitting of arbitrary multi-project prose
is not claimed. Client consent and authoritative status review remain human tasks.

Multi-project assignment transactions are atomic per project, not across all
projects at once. A partial failure leaves the source pending for retry; replay
skips projects that already committed, then completes the remaining assignments.

SQL migration execution and all live Gmail/Supabase/GitHub checks remain pending
team test-account configuration. SQL is not proven by Python fake-store tests.
The earlier fresh-agent test used the original single-project fixture; repeat it
in a generated customer repo after reviewing and merging its context PR.
