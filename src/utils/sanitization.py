"""Input sanitization and safety utilities for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 8.
"""

from __future__ import annotations

import re

from src.state.exceptions import StateValidationError

E164_REGEX = re.compile(r"^\+[1-9][0-9]{1,14}$", re.ASCII)
IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
PHONE_REDACTION_PATTERN = re.compile(r"\+?[0-9]{7,15}", re.ASCII)

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"<script.*?>", re.IGNORECASE),
    re.compile(r"assistant\s*:", re.IGNORECASE),
    re.compile(r"new\s+rule\s*:", re.IGNORECASE),
]


def mask_phone(phone: str | None) -> str:
    """Mask phone number for safe logging (e.g. +13035550147 -> +1303***0147)."""
    if not phone or not isinstance(phone, str):
        return ""
    clean = phone.strip()
    if len(clean) >= 8:
        return f"{clean[:5]}***{clean[-4:]}"
    elif len(clean) >= 4:
        return f"{clean[:2]}***{clean[-2:]}"
    return "***"


def redact_phone_numbers(text_or_obj: any) -> any:
    """Recursively redact phone numbers in strings, dictionaries, or lists."""
    if isinstance(text_or_obj, str):
        return PHONE_REDACTION_PATTERN.sub(lambda m: mask_phone(m.group(0)), text_or_obj)
    elif isinstance(text_or_obj, dict):
        return {k: redact_phone_numbers(v) for k, v in text_or_obj.items()}
    elif isinstance(text_or_obj, list):
        return [redact_phone_numbers(item) for item in text_or_obj]
    return text_or_obj


def sanitize_error_message(error_msg: str) -> str:
    """Sanitize raw error messages to avoid leaking API tokens, sensitive headers, or raw phone numbers."""
    if not error_msg:
        return ""
    # Strip potential Bearer tokens or secret keys
    sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", r"\1[REDACTED]", error_msg)
    sanitized = re.sub(
        r"(api[_-]?key\s*[:=]\s*)[A-Za-z0-9_\-\.]{8,}",
        r"\1[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Redact raw phone numbers (replace matches of \+?[0-9]{7,15} with masked versions like +1303***0147)
    sanitized = redact_phone_numbers(sanitized)
    return sanitized


def validate_e164_phone(phone: str) -> bool:
    """Validate that phone number adheres strictly to ASCII-only E.164 format."""
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
