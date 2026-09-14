"""CALL-E Driver Interrogation node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 3)
- DOCS/AGENT_LOGIC_SPEC.md Section 3, Section 6, Section 8
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from src.state.exceptions import CallEAttemptExhaustedError, StateValidationError
from src.state.schema import (
    AuditEvent,
    CallEvidence,
    ErrorRecord,
    PhysicalObservations,
    SentinelState,
    ToolCallResult,
)
from src.tools.call_e_client import call_e_initiate_triage
from src.tools.schemas.call_e_initiate_triage import (
    CALLE_TRIAGE_RESULT_JSON_SCHEMA,
    CallERecipient,
    CallETriageInput,
)
from src.utils.sanitization import sanitize_interpolated_text, validate_e164_phone


def build_triage_task_instructions(state: SentinelState) -> str:
    """Build deterministic, prompt-injection sanitized task instructions for CALL-E."""
    event_id = state.get("event_id", "")
    truck_id = sanitize_interpolated_text(str(state.get("truck_id", "")))
    trailer_id = sanitize_interpolated_text(str(state.get("trailer_id", "")))
    driver_name = sanitize_interpolated_text(str(state.get("driver_name", "Driver")))
    alarm_code = sanitize_interpolated_text(str(state.get("telematics_alarm_code", "UNKNOWN")))
    current_temp = state.get("current_temp_f", 0.0)
    setpoint = state.get("setpoint_temp_f", 0.0)
    nearest_hub = sanitize_interpolated_text(str(state.get("nearest_verified_cold_hub", "nearest cold hub")))

    return (
        f"speak with commercial driver {driver_name} regarding a critical reefer temperature excursion on truck {truck_id}, trailer {trailer_id}. "
        f"Current reefer temp is {current_temp}F with setpoint {setpoint}F (telematics alarm: {alarm_code}). "
        f"You must ask the driver: "
        f"1. Are they parked in a safe location? "
        f"2. Is the reefer diesel engine running? "
        f"3. Is the return air bulkhead clear or obstructed? "
        f"4. Is there visible cargo sweating or frost on evaporator coils? "
        f"5. Does the reefer display any active alarm codes? "
        f"6. How many FMCSA driving hours/minutes remain on their electronic logbook? "
        f"7. Does an active emergency (fire, collision, medical) exist? "
        f"Offer options to divert to {nearest_hub} or request roadside service, and record their agreed choice. "
        f"Prohibit DIY mechanical repairs and do not discuss cargo claims. "
        f"On completion, record their responses in the structured result. If the call cannot be completed, record the failure reason."
    )


def is_dummy_mock_phone(phone: str | None) -> bool:
    """Check if phone number is a fictional/dummy mock number (e.g. +12065550198 or containing 555)."""
    if not phone:
        return True
    cleaned = phone.strip()
    return cleaned == "+12065550198" or "555" in cleaned or "0000000" in cleaned


async def call_interrogation_node(state: SentinelState) -> dict[str, Any]:
    """Execute single outbound CALL-E triage call to the commercial driver.

    Enforces:
    - Zero-Redial policy (exactly 1 call per event_id)
    - Non-LLM deterministic invocation
    - Bound ONLY to call_e_initiate_triage
    """
    event_id = state.get("event_id", "")
    incoming_phone = state.get("driver_phone_e164", "")
    locale = state.get("driver_locale", "en-US")

    # Zero-Redial guard check
    if state.get("call_id") is not None:
        raise CallEAttemptExhaustedError(
            f"Zero-Redial violation: call_id '{state.get('call_id')}' already exists for event_id '{event_id}'."
        )

    # Resolve target phone number:
    # Check if TMS enrichment provided a confirmed driver phone
    confirmed_phone = None
    tms_artifact = state.get("tool_artifacts", {}).get("tms_lookup_driver_and_load")
    if tms_artifact:
        payload = tms_artifact.payload if hasattr(tms_artifact, "payload") else tms_artifact.get("payload")
        if isinstance(payload, dict):
            confirmed_phone = payload.get("driver_phone_e164_confirmed")

    # Resolution priority:
    # If the incoming event contains an explicit driver_phone_e164 (or if driver_phone_e164_confirmed
    # matches dummy mock patterns like +12065550198 or 555), it must use the actual incoming driver_phone_e164.
    if incoming_phone and validate_e164_phone(incoming_phone):
        if not confirmed_phone or is_dummy_mock_phone(confirmed_phone) or incoming_phone:
            target_phone = incoming_phone
    elif confirmed_phone and validate_e164_phone(confirmed_phone) and not is_dummy_mock_phone(confirmed_phone):
        target_phone = confirmed_phone
    else:
        target_phone = incoming_phone

    logger.info(f"[CALL-E Dispatch] Target phone number: {target_phone}")

    if not target_phone or not validate_e164_phone(target_phone):
        raise StateValidationError(f"Call interrogation requires valid E.164 phone, got '{target_phone}'")

    derived_region = "IN" if target_phone.startswith("+91") else "US"
    recipient = CallERecipient(
        phone=target_phone,
        region=derived_region,
        locale=locale,
    )
    task_instructions = build_triage_task_instructions(state)
    call_input = CallETriageInput(
        recipient_phone_e164=target_phone,
        driver_locale=locale,
        task_instructions=task_instructions,
        result_schema=CALLE_TRIAGE_RESULT_JSON_SCHEMA,
        recipient=recipient,
    )

    t0 = time.perf_counter()
    output = await call_e_initiate_triage(call_input)
    latency_ms = (time.perf_counter() - t0) * 1000

    tool_artifacts: dict[str, ToolCallResult] = {}
    error_logs: list[ErrorRecord] = []
    escalation_reasons: list[str] = []
    requires_override = False

    tool_artifacts["call_e_initiate_triage"] = ToolCallResult(
        tool_call_id=f"calle_{event_id}",
        tool_name="call_e_initiate_triage",
        status="SUCCESS" if output.status == "completed" and output.task_completed else "FAILED",
        payload=output.model_dump(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        latency_ms=latency_ms,
    )

    if output.status != "completed" or not output.task_completed or output.structured_result is None:
        error_logs.append(
            ErrorRecord(
                node_name="call_interrogation",
                error_type="TelephonyTriageIncomplete",
                message=output.error or f"Call completed with non-terminal status '{output.status}' or incomplete task",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        if output.status != "completed":
            escalation_reasons.append(f"call_status_{output.status}")
        else:
            escalation_reasons.append("telephony_triage_incomplete")
        requires_override = True

        audit_event = AuditEvent(
            event_type="NODE_COMPLETED",
            node_name="call_interrogation",
            timestamp=datetime.now(timezone.utc).isoformat(),
            details={
                "call_id": output.call_id,
                "status": output.status,
                "task_completed": output.task_completed,
                "requires_override": True,
            },
        )

        return {
            "call_id": output.call_id,
            "call_status": output.status,
            "driver_contacted": output.status == "completed",
            "agreed_action": "ESCALATE_TO_HUMAN_DISPATCH",
            "disposition": "ESCALATED_TELEPHONY_FAILURE",
            "tool_artifacts": tool_artifacts,
            "error_logs": error_logs,
            "escalation_reasons": escalation_reasons,
            "requires_immediate_human_override": True,
            "audit_trail": [audit_event],
        }

    # Successful call extraction
    sr = output.structured_result
    physical_obs = PhysicalObservations(
        air_bulkhead_obstructed=sr.air_bulkhead_obstructed,
        cargo_sweating_detected=sr.cargo_sweating_detected,
        evaporator_ice_detected=sr.evaporator_ice_detected,
        display_error_codes=[sr.driver_reported_alarm_code] if sr.driver_reported_alarm_code else [],
        fuel_level_sufficient=sr.fuel_level_sufficient,
        driver_action_taken=sr.driver_action_taken or "None",
    )

    ev_data = output.evidence or {}
    evidence_ref = str(ev_data.get("transcript_or_evidence_ref", f"evd_{output.call_id}"))
    duration_secs = int(ev_data.get("call_duration_seconds", 0))

    call_evidence = CallEvidence(
        transcript_or_evidence_ref=evidence_ref,
        completion_confidence=output.completion_confidence,
        task_completed=output.task_completed,
        call_duration_seconds=duration_secs,
    )

    if sr.emergency_reported:
        escalation_reasons.append("emergency_reported_on_call")
        requires_override = True

    audit_event = AuditEvent(
        event_type="NODE_COMPLETED",
        node_name="call_interrogation",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details={
            "call_id": output.call_id,
            "status": output.status,
            "task_completed": output.task_completed,
            "driver_hos_minutes_remaining": sr.driver_hos_minutes_remaining,
            "selected_option": sr.selected_option,
            "emergency_reported": sr.emergency_reported,
        },
    )

    updates: dict[str, Any] = {
        "call_id": output.call_id,
        "call_status": output.status,
        "driver_contacted": True,
        "driver_reported_alarm_code": sr.driver_reported_alarm_code,
        "physical_observations": physical_obs,
        "driver_hos_minutes_remaining": sr.driver_hos_minutes_remaining,
        "call_evidence": call_evidence,
        "tool_artifacts": tool_artifacts,
        "audit_trail": [audit_event],
    }

    if escalation_reasons:
        updates["escalation_reasons"] = escalation_reasons
    if requires_override:
        updates["requires_immediate_human_override"] = True

    return updates
