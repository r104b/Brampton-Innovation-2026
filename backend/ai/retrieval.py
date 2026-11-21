"""Project state and pending-review projection."""

import json

from backend.models.schemas import ProjectState

COLLECTIONS = {"deliverable": "deliverables", "question": "questions", "decision": "decisions"}
WARNING_FIELDS = ("id", "item_type", "item_id", "reason", "proposed_change", "created_at", "evidence")


def project_state(snapshot: dict) -> ProjectState:
    fields = ("project_id", "project_name", "project_summary", "version", "as_of")
    result = {field: snapshot[field] for field in fields}
    result["schema_version"] = 1
    for collection in COLLECTIONS.values():
        result[collection] = [
            {key: value for key, value in row.items() if key != "match_key"}
            for row in snapshot[collection]
        ]
    result["review_warnings"] = [
        {field: review[field] for field in WARNING_FIELDS}
        for review in snapshot["reviews"]
        if review["status"] == "pending" and review["item_id"] is not None
    ]
    for collection in [*COLLECTIONS.values(), "review_warnings"]:
        result[collection].sort(key=lambda record: record["id"])
        for record in result[collection]:
            record["evidence"] = sorted(
                record["evidence"], key=lambda ref: (ref["source_id"], ref["evidence_id"])
            )
    return ProjectState.model_validate_json(json.dumps(result))
