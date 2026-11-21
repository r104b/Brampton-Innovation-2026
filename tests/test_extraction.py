import json

import pytest
from pydantic import ValidationError

from backend.ai.extractor import GeminiExtractor, parse_items
from backend.models.schemas import EmailPayload


def test_extraction_uses_structured_output_without_network():
    email = EmailPayload.model_validate_json(json.dumps({
        "source_id": "EMAIL-002", "project_id": "maple-grove-demo",
        "source_type": "email", "subject": "SMS confirmations",
        "sender": "jordan.lee@example.test", "received_at": "2026-11-17T19:40:00Z",
        "body": "Please add an SMS confirmation whenever a patient successfully books an appointment.",
    }))

    def generate(prompt, schema):
        assert email.body in prompt
        assert email.sender not in prompt
        assert "untrusted" in prompt
        assert schema["type"] == "array"
        return json.dumps([{
            "type": "deliverable", "title": "SMS confirmations",
            "description": "Confirm appointments by SMS.", "proposed_status": None,
            "source_id": email.source_id, "source_quote": email.body, "requires_review": False,
        }])

    items = GeminiExtractor("fake", "fixture", generate)(email)
    assert items[0].source_quote == email.body


@pytest.mark.parametrize("raw", ["{}", "[{}]", "invalid"])
def test_invalid_structured_output_is_rejected(raw):
    with pytest.raises(ValidationError):
        parse_items(raw)
