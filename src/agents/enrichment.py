"""TMS and ELD Enrichment node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 2)
- DOCS/AGENT_LOGIC_SPEC.md Section 6
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any

from src.state.schema import AuditEvent, ErrorRecord, SentinelState, ToolCallResult
from src.tools.eld_client import eld_lookup_hos_minutes
from src.tools.schemas.eld_lookup_hos_minutes import ELDLookupInput
from src.tools.schemas.tms_lookup_driver_and_load import TMSLookupInput
from src.tools.tms_client import tms_lookup_driver_and_load


async def enrichment_node(state: SentinelState) -> dict[str, Any]:
    """Execute parallel TMS driver/load lookup and ELD HOS query.

    Non-LLM deterministic node. Bound ONLY to:
    - tms_lookup_driver_and_load
    - eld_lookup_hos_minutes
    """
    event_id = state.get("event_id", "")
    truck_id = state.get("truck_id", "")
    trailer_id = state.get("trailer_id", "")

    phone = state.get("driver_phone_e164", "")
    driver_name = state.get("driver_name")

    tms_input = TMSLookupInput(
        truck_id=truck_id,
        trailer_id=trailer_id,
        event_id=event_id,
        driver_phone_e164=phone if phone else None,
        driver_name=driver_name if driver_name else None,
    )
    eld_input = ELDLookupInput(truck_id=truck_id, driver_phone_e164=phone)

    tool_artifacts: dict[str, ToolCallResult] = {}
    error_logs: list[ErrorRecord] = []
    escalation_reasons: list[str] = []
    requires_override = False

    tms_output = None
    eld_output = None

    # Execute TMS and ELD lookups in parallel
    t0 = time.perf_counter()
    results = await asyncio.gather(
        tms_lookup_driver_and_load(tms_input),
        eld_lookup_hos_minutes(eld_input),
        return_exceptions=True,
    )
    tms_res, eld_res = results

    # Process TMS result
    tms_latency = (time.perf_counter() - t0) * 1000
    if isinstance(tms_res, Exception):
        error_logs.append(
            ErrorRecord(
                node_name="enrichment",
                error_type="TMSLookupError",
                message=str(tms_res),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        tool_artifacts["tms_lookup_driver_and_load"] = ToolCallResult(
            tool_call_id=f"tms_{event_id}",
            tool_name="tms_lookup_driver_and_load",
            status="FAILED",
            payload={"error": str(tms_res)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=tms_latency,
        )
        escalation_reasons.append("tms_lookup_failed")
        requires_override = True
    else:
        tms_output = tms_res
        tool_artifacts["tms_lookup_driver_and_load"] = ToolCallResult(
            tool_call_id=f"tms_{event_id}",
            tool_name="tms_lookup_driver_and_load",
            status="SUCCESS",
            payload=tms_output.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=tms_latency,
        )
        if not tms_output.tms_verified:
            escalation_reasons.append("tms_verification_failed")
            requires_override = True

    # Process ELD result
    eld_latency = (time.perf_counter() - t0) * 1000
    if isinstance(eld_res, Exception):
        error_logs.append(
            ErrorRecord(
                node_name="enrichment",
                error_type="ELDLookupError",
                message=str(eld_res),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        tool_artifacts["eld_lookup_hos_minutes"] = ToolCallResult(
            tool_call_id=f"eld_{event_id}",
            tool_name="eld_lookup_hos_minutes",
            status="FAILED",
            payload={"error": str(eld_res)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=eld_latency,
        )
        escalation_reasons.append("eld_lookup_failed")
        requires_override = True
    else:
        eld_output = eld_res
        tool_artifacts["eld_lookup_hos_minutes"] = ToolCallResult(
            tool_call_id=f"eld_{event_id}",
            tool_name="eld_lookup_hos_minutes",
            status="SUCCESS",
            payload=eld_output.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=eld_latency,
        )

    tms_verified = tms_output.tms_verified if tms_output else False
    eld_hos_minutes = eld_output.hos_minutes_remaining if eld_output else None
    nearest_hub = (
        tms_output.nearest_verified_cold_hub.name
        if tms_output and tms_output.nearest_verified_cold_hub
        else None
    )

    audit_event = AuditEvent(
        event_type="NODE_COMPLETED",
        node_name="enrichment",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details={
            "tms_verified": tms_verified,
            "eld_hos_minutes_at_dispatch": eld_hos_minutes,
            "nearest_verified_cold_hub": nearest_hub,
            "requires_override": requires_override,
        },
    )

    updates: dict[str, Any] = {
        "tms_verified": tms_verified,
        "eld_hos_minutes_at_dispatch": eld_hos_minutes,
        "nearest_verified_cold_hub": nearest_hub,
        "tool_artifacts": tool_artifacts,
        "audit_trail": [audit_event],
    }

    if error_logs:
        updates["error_logs"] = error_logs
    if escalation_reasons:
        updates["escalation_reasons"] = escalation_reasons
    if requires_override:
        updates["requires_immediate_human_override"] = True

    return updates
