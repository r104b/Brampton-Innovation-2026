"""Conservative matching of known requirement and question titles."""

import re
import unicodedata

ALIASES = {
    "sms confirmation": "sms booking confirmations",
    "sms confirmations": "sms booking confirmations",
    "patient registration sign in": "patient registration and sign in",
    "which sms provider should we use": "which sms provider should be used",
    "do you have approved wording for the confirmation message":
        "what wording should sms confirmation contain",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[^\W_]+", text))


def match_key(text: str) -> str:
    normalized = normalize(text)
    return ALIASES.get(normalized, normalized)
