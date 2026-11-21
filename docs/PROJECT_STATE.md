# Project-state contract, schema version 1

Person B produces this read model; Person C consumes it without AI calls or
database writes. `GET /api/projects/{id}/state` returns the same model that the
read-only memory service returns. The Python service interface is
`get_project_state(project_id: str) -> ProjectState`; sync versus async wiring
is left to the endpoint implementation. No service implementation is added here.

This extends section 2 of the work plan with team implementation decisions.
Models in `backend/models/schemas.py` are authoritative for field validation.
Every field is required, including explicit `null` values and empty arrays.
Unknown fields are rejected. All timestamps must include a timezone; producers
should serialize them in UTC. IDs are nonempty opaque strings, stable across
updates and replays. Do not derive IDs from array order or mutable titles.

## Snapshot envelope

| Field | Meaning |
| --- | --- |
| `schema_version` | Literal `1`; describes this JSON format, independently of state version |
| `project_id`, `project_name` | Authorized project identity and display name |
| `project_summary` | Stored, approved project description; empty string if unknown |
| `version` | Nonnegative per-project revision; starts at zero |
| `as_of` | Time of the most recent committed snapshot change, or project creation for version zero |
| `deliverables` | All current work records, including implemented and verified work |
| `questions` | Open and answered questions |
| `decisions` | Active and superseded decisions; retain history |
| `review_warnings` | Pending human reviews only; excludes resolved/rejected review entries |

Person B increments `version` once per committed transaction that changes any
exported state, including evidence and review warnings. Replayed inputs and
read-only requests do not increment it. Update `as_of` in that transaction,
not when the snapshot is fetched. Read the envelope and all collections from a
consistent database snapshot. Do not use wall-clock generation time as version.
Return a not-found error for an unknown project, never an empty successful state.

Person B sorts each collection by `id` and evidence by `(source_id, evidence_id)`;
Person C also sorts when rendering to make output independent of input ordering.
Repeated reads of an unchanged version should yield equivalent content.

## Evidence and common record fields

Deliverables, questions, and decisions each contain `id`, `updated_at`, and a
nonempty `evidence` array, plus the fields below. Each evidence reference has:

| Field | Meaning |
| --- | --- |
| `evidence_id` | Stable ID of an evidence row |
| `source_id` | Public source identifier, such as the ingestion payload's Gmail message ID; not an internal database foreign-key UUID unless that is also the public ID |
| `kind` | `requirement`, `implementation`, `qa_result`, `client_answer`, or `decision` |

These references contain no raw body, email address, token, or source quote.
Exact quotes and offsets remain in Person B's evidence storage. Person B must
verify source spans, ownership, evidence type, and approvals before exporting a
record. A `qa_result` label alone is not proof of successful QA: it may be emitted
for a verified status only after Person B validates a passing result for that work.
The model checks shape and references; it cannot authenticate evidence or consent.

All nested records and referenced sources must belong to the authorized project.
Person B enforces this in queries; Person A enforces request authorization.
Public strings must be curated for context export. Omitting raw bodies does not
automatically redact a secret embedded in a title; Person C must apply export
security checks too. Source text is untrusted data, never agent instructions.

## Deliverables

Fields: `title`, `description`, `status`, `blocked_reason` (string or null).
Statuses: `open`, `in_progress`, `implemented`, `verified`, `blocked`.

`implemented` means code exists; `verified` requires validated passing QA evidence.
The model rejects verified records without a `qa_result` reference. A blocked
record requires a nonempty `blocked_reason`; all other statuses require null.
Person B owns transition validation and preserving completed work. Client approval
does not imply QA verification. A warning must not silently change work status.

## Questions

Fields: `question`, `state` (`open` or `answered`), `requires_client_consent`
(boolean), `answer` (string or null), `answered_source_id` (string or null).

Open questions have null answer fields. Answered questions require an answer and
a matching `client_answer` evidence reference for `answered_source_id`.
Person B verifies the answer and any required consent came from an authorized
human; the boolean is a requirement flag, not an approval flag. Repeated questions
retain their original ID and accumulate evidence. A proposed answer stays in
review until approved, leaving the question open.

## Decisions

Fields: `statement`, `state` (`active` or `superseded`), `supersedes_id` (ID or null).
The newer decision points backward to the decision it replaces. Both remain in
the snapshot; the predecessor is marked `superseded` in the same transaction.
References must exist within this project's decisions and must not form cycles.
A conflict awaiting review leaves the last approved active decision unchanged.

## Pending reviews

Each warning has `id`, `item_type` (`deliverable`, `question`, or `decision`),
`item_id`, `reason`, `proposed_change` (display text), `created_at`, and nonempty
`evidence`. Its target must exist in the corresponding snapshot collection.
Record IDs are unique within each collection. New ambiguous proposals without
an existing target stay in the database review queue until an approved record
exists; this version exposes warnings attached to existing records only.

Person C displays the proposal as pending, alongside the approved state, never
as an applied fact. Resolved reviews disappear on the next committed version;
Person B retains their history in the database audit trail.

## Integration handoff

`sample-data/project-state.json` includes all five work statuses, an unanswered
consent question, a sourced answer, superseded decision history, and a pending
conflict. All content and evidence identifiers are fictional fixture data.

Person B maps database rows into these types and enforces transactions, source
validation, authorization, transitions, and revisions. Person C can now build
the deterministic renderer against this fixture. Neither the fixture nor model
validation constitutes a running database or endpoint implementation.

Changes to this format require a coordinated PR and updated fixtures/tests.
Breaking changes increment `schema_version`; project data changes increment
`version`. No teammate approval is implied by adding this baseline to the repo.
