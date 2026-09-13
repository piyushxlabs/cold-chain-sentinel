"""Escalation Failure node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 7)
- DOCS/AGENT_LOGIC_SPEC.md Section 6, Section 8
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from src.state.schema import AuditEvent, ErrorRecord, SentinelState, ToolCallResult
from src.tools.ops_alert_client import ops_alert_escalate
from src.tools.schemas.ops_alert_escalate import OpsAlertInput


async def escalation_failure_node(state: SentinelState) -> dict[str, Any]:
    """Dispatch P0 operations alert for human intervention and lock override flag.

    Non-LLM deterministic node. Bound ONLY to ops_alert_escalate.
    """
    event_id = state.get("event_id", "")
    escalation_reasons = state.get("escalation_reasons", [])
    if not escalation_reasons:
        escalation_reasons = ["unspecified_safety_gate_trip"]

    state_summary = {
        "truck_id": state.get("truck_id"),
        "trailer_id": state.get("trailer_id"),
        "driver_phone_e164": state.get("driver_phone_e164"),
        "current_temp_f": state.get("current_temp_f"),
        "setpoint_temp_f": state.get("setpoint_temp_f"),
        "driver_hos_minutes_remaining": state.get("driver_hos_minutes_remaining"),
        "call_status": state.get("call_status"),
        "disposition": state.get("disposition"),
    }

    t0 = time.perf_counter()
    output = await ops_alert_escalate(
        OpsAlertInput(
            event_id=event_id,
            escalation_reasons=escalation_reasons,
            severity_level="P0_CRITICAL",
            state_summary=state_summary,
        )
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    tool_artifacts = {
        "ops_alert_escalate": ToolCallResult(
            tool_call_id=f"alert_{event_id}",
            tool_name="ops_alert_escalate",
            status="SUCCESS" if output.delivered else "FAILED",
            payload=output.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
        )
    }

    audit_event = AuditEvent(
        event_type="ESCALATION_FIRED",
        node_name="escalation_failure",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details={
            "alert_id": output.alert_id,
            "delivered": output.delivered,
            "channel": output.channel,
            "escalation_reasons": escalation_reasons,
        },
    )

    return {
        "agreed_action": "ESCALATE_TO_HUMAN_DISPATCH",
        "requires_immediate_human_override": True,
        "escalation_reasons": escalation_reasons,
        "tool_artifacts": tool_artifacts,
        "audit_trail": [audit_event],
    }
