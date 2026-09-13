"""Persistence and Audit terminal node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 8)
- DOCS/AGENT_LOGIC_SPEC.md Section 6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.state.schema import AuditEvent, SentinelState


async def persistence_audit_node(state: SentinelState) -> dict[str, Any]:
    """Assemble final Deliverable Contract payload and record terminal audit event.

    Non-LLM deterministic terminal node.
    """
    event_id = state.get("event_id", "")
    now = datetime.now(timezone.utc)

    audit_event = AuditEvent(
        event_type="SESSION_PERSISTED",
        node_name="persistence_audit",
        timestamp=now.isoformat(),
        details={
            "event_id": event_id,
            "disposition": state.get("disposition"),
            "agreed_action": state.get("agreed_action"),
            "requires_override": state.get("requires_immediate_human_override", False),
            "call_id": state.get("call_id"),
        },
    )

    return {
        "execution_timestamp": now,
        "audit_trail": [audit_event],
    }
