# Brampton-Innovation-2026

Before splitting implementation work, read [the shared contracts](docs/CONTRACTS.md).
Shared Pydantic models live in `backend/models/schemas.py`; synthetic handshake
examples live in `sample-data/contracts.json`. The API and services are scaffolds
to be implemented by the three workstream owners.

## Generate the context snapshot

From the repository root, using the shared dependencies:

```sh
python -m pip install -r backend/requirements.txt
python -m backend.services.context_generator --input sample-data/project-state.json --output context/CURRENT_STATE.md --fixture
```

The checked-in snapshot is explicitly labeled as fictional demonstration data.
The generator makes no database or LLM calls. Person B's eventual state reader
can pass a validated `ProjectState` to
`backend.services.context_generator.render_context(state)` for live rendering.
The API and database integration are still to be implemented.

Output is sorted and uses the state's timestamp/version, so unchanged state
produces identical Markdown. Implemented work, QA-verified work, unanswered
questions, decision history, and pending proposals remain separate. Public text
is escaped, and common token, private-key, and email patterns are redacted.
This pattern filter cannot recognize every secret or personal detail; producers
must still supply curated export-safe fields. Text remains untrusted data even
after Markdown escaping.

Run offline checks with:

```sh
python -m pytest tests -q -p no:cacheprovider
```
