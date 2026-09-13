"""Deterministic Decision Gate node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 5)
- DOCS/AGENT_LOGIC_SPEC.md Section 6, Section 8
- RULE: code-level-verification-over-model-discretion.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.state.schema import AgreedAction, AuditEvent, Disposition, SentinelState


async def decision_gate_node(state: SentinelState) -> dict[str, Any]:
    """Evaluate compliance rules in strict priority order.

    Non-LLM deterministic node. ZERO external tools bound.
    Enforces:
    1. Active Emergency / Prior Override Gate
    2. Driver Refusal / Dispute Gate
    3. FMCSA 49 CFR Part 395 HOS Gate (< 35 min remaining)
    4. FSMA Biologics/Pharma Cargo Sweating Spoilage Gate
    5. Injection / Low Confidence Gate
    6. Roadside Service vs Autonomous Cold Hub Divert vs Continue
    """
    escalation_reasons: list[str] = []
    requires_override = state.get("requires_immediate_human_override", False)

    config = state.get("config")
    min_hos = config.min_hos_minutes_for_reroute if config else 35

    cargo = state.get("cargo_manifest")
    observations = state.get("physical_observations")
    driver_hos = state.get("driver_hos_minutes_remaining")
    compliance = state.get("compliance_review")
    tool_artifacts = state.get("tool_artifacts", {})

    # Extract CALL-E structured result if available
    calle_artifact = tool_artifacts.get("call_e_initiate_triage")
    structured_res = (
        calle_artifact.payload.get("structured_result")
        if calle_artifact and isinstance(calle_artifact.payload, dict)
        else None
    )

    selected_option = (
        structured_res.get("selected_option")
        if structured_res and isinstance(structured_res, dict)
        else "DIVERT_TO_COLD_HUB"
    )
    emergency_reported = (
        structured_res.get("emergency_reported", False)
        if structured_res and isinstance(structured_res, dict)
        else False
    )

    agreed_action: AgreedAction
    disposition: Disposition

    # Gate 1: Active Emergency Reported on Call
    if emergency_reported:
        agreed_action = "ESCALATE_TO_HUMAN_DISPATCH"
        disposition = "ESCALATED_MANUAL_OVERRIDE"
        requires_override = True
        escalation_reasons.append("emergency_reported_on_call")

    # Gate 2: Driver Refusal / Dispute
    elif selected_option == "DRIVER_REFUSED":
        agreed_action = "DRIVER_REFUSED"
        disposition = "ESCALATED_DRIVER_REFUSAL"
        requires_override = True
        escalation_reasons.append("driver_refused_reroute")

    # Gate 3: FMCSA 49 CFR Part 395 HOS Gate (< 35 min remaining)
    elif driver_hos is None or driver_hos < min_hos:
        agreed_action = "ESCALATE_TO_HUMAN_DISPATCH"
        disposition = "ESCALATED_HOS_BREACH"
        requires_override = True
        escalation_reasons.append(f"insufficient_hos_for_reroute_{driver_hos}m_lt_{min_hos}m")

    # Gate 4: FSMA Biologics/Pharma Cargo Sweating Spoilage Gate
    elif (
        cargo
        and cargo.commodity_type in ["Biologics", "Pharma"]
        and observations
        and observations.cargo_sweating_detected
    ):
        agreed_action = "ESCALATE_TO_HUMAN_DISPATCH"
        disposition = "ESCALATED_CARGO_SPOILAGE_RISK"
        requires_override = True
        escalation_reasons.append("biologics_cargo_sweating_detected")

    # Gate 5: Prompt Injection / Low Confidence Gate
    elif compliance and (compliance.suspected_injection or compliance.review_confidence < 0.5):
        agreed_action = "ESCALATE_TO_HUMAN_DISPATCH"
        disposition = "ESCALATED_INJECTION_DETECTED"
        requires_override = True
        if compliance.suspected_injection:
            escalation_reasons.append("suspected_prompt_injection")
        else:
            escalation_reasons.append("unresolved_low_confidence_review")

    # Gate 6: Prior Locked Override (manual cancellation / upstream fault)
    elif requires_override:
        agreed_action = "ESCALATE_TO_HUMAN_DISPATCH"
        disposition = "ESCALATED_MANUAL_OVERRIDE"
        requires_override = True
        if "manual_override" not in escalation_reasons:
            escalation_reasons.append("manual_override")

    # Gate 7: Pull Over for Roadside Service
    elif selected_option in ["PULL_OVER_ROADSIDE_SERVICE", "PULL_OVER"]:
        agreed_action = "PULL_OVER_ROADSIDE_SERVICE"
        disposition = "AUTONOMOUSLY_SERVICED"

    # Gate 8: Autonomous Divert to Emergency Cold Hub
    elif selected_option in ["DIVERT_TO_COLD_HUB", "DIVERT_TO_EMERGENCY_COLD_HUB"]:
        agreed_action = "DIVERT_TO_EMERGENCY_COLD_HUB"
        disposition = "AUTONOMOUSLY_DIVERTED"

    # Gate 9: Continue Monitored Route
    else:
        agreed_action = "CONTINUE_MONITORED_ROUTE"
        disposition = "AUTONOMOUSLY_RESOLVED_CONTINUE"

    audit_event = AuditEvent(
        event_type="NODE_COMPLETED",
        node_name="decision_gate",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details={
            "agreed_action": agreed_action,
            "disposition": disposition,
            "requires_immediate_human_override": requires_override,
            "escalation_reasons": escalation_reasons,
        },
    )

    updates: dict[str, Any] = {
        "agreed_action": agreed_action,
        "disposition": disposition,
        "audit_trail": [audit_event],
    }

    if requires_override:
        updates["requires_immediate_human_override"] = True
    if escalation_reasons:
        updates["escalation_reasons"] = escalation_reasons

    return updates
