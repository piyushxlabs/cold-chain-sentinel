"""Input sanitization and safety utilities for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 8.
"""

from __future__ import annotations

import re

from src.state.exceptions import StateValidationError

E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")
IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"<script.*?>", re.IGNORECASE),
    re.compile(r"assistant\s*:", re.IGNORECASE),
    re.compile(r"new\s+rule\s*:", re.IGNORECASE),
]


def validate_e164_phone(phone: str) -> bool:
    """Validate that phone number adheres strictly to E.164 format."""
    if not phone or not isinstance(phone, str):
        return False
    return bool(E164_REGEX.match(phone.strip()))


def validate_identifier(identifier: str) -> bool:
    """Validate that structured IDs contain only safe alphanumeric and punctuation characters."""
    if not identifier or not isinstance(identifier, str):
        return False
    return bool(IDENTIFIER_REGEX.match(identifier.strip()))


def sanitize_interpolated_text(text: str) -> str:
    """Screen and sanitize external text before interpolation into task prompts or tool payloads.

    Raises:
        StateValidationError: If prompt injection or scope override patterns are detected.
    """
    if not text or not isinstance(text, str):
        return ""

    cleaned = text.strip()
    for pattern in INJECTION_PATTERNS:
        if pattern.search(cleaned):
            raise StateValidationError(
                f"Security violation: prompt injection pattern detected in input text: '{cleaned}'"
            )
    return cleaned


def wrap_in_data_tags(tag_name: str, content: str) -> str:
    """Wrap untrusted content in XML data tags for model defense-in-depth."""
    clean_tag = re.sub(r"[^a-zA-Z0-9_]", "", tag_name)
    return f"<{clean_tag}>\n{content}\n</{clean_tag}>"
