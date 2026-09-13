"""Webhook Ingress node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 1)
- DOCS/AGENT_LOGIC_SPEC.md Section 6, Section 8
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.state.exceptions import StateValidationError
from src.state.schema import AuditEvent, RuntimeConfig, SentinelState
from src.utils.sanitization import sanitize_interpolated_text, validate_e164_phone


async def ingress_node(state: SentinelState) -> dict[str, Any]:
    """Validate webhook payload and initialize immutable state and config.

    Non-LLM deterministic node. Zero tool calls.
    """
    event_id = state.get("event_id")
    if not event_id:
        raise StateValidationError("Webhook ingress missing required field 'event_id'")

    truck_id = state.get("truck_id")
    if not truck_id:
        raise StateValidationError("Webhook ingress missing required field 'truck_id'")

    trailer_id = state.get("trailer_id")
    if not trailer_id:
        raise StateValidationError("Webhook ingress missing required field 'trailer_id'")

    phone = state.get("driver_phone_e164")
    if not phone or not validate_e164_phone(phone):
        raise StateValidationError(f"Webhook ingress invalid E.164 driver phone: {phone}")

    cargo = state.get("cargo_manifest")
    if not cargo:
        raise StateValidationError("Webhook ingress missing required field 'cargo_manifest'")

    # Initialize runtime config if not already provided
    config = state.get("config")
    if not config:
        config = RuntimeConfig(
            trace_id=f"trc_{event_id}",
            client_mode="mock",
            max_tool_retry_attempts=3,
            min_hos_minutes_for_reroute=35,
        )

    timestamp_str = datetime.now(timezone.utc).isoformat()
    audit_event = AuditEvent(
        event_type="NODE_ENTERED",
        node_name="ingress",
        timestamp=timestamp_str,
        details={
            "event_id": event_id,
            "truck_id": truck_id,
            "trailer_id": trailer_id,
            "driver_phone_e164": phone,
        },
    )

    return {
        "config": config,
        "audit_trail": [audit_event],
    }
