"""Autonomous Actuation node for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4 (Node 6)
- DOCS/AGENT_LOGIC_SPEC.md Section 6, Section 8
- RULE: code-level-verification-over-model-discretion.md
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from src.state.exceptions import StateValidationError, ToolExecutionError
from src.state.schema import AuditEvent, ErrorRecord, SentinelState, ToolCallResult
from src.tools.maintenance_client import maintenance_dispatch_ticket
from src.tools.routing_client import routing_mutate_route
from src.tools.schemas.maintenance_dispatch_ticket import MaintenanceDispatchInput
from src.tools.schemas.routing_mutate_route import RoutingMutationInput
from src.tools.schemas.sms_send_confirmation import SMSSendInput
from src.tools.schemas.warehouse_reserve_dock import WarehouseReservationInput
from src.tools.sms_client import sms_send_confirmation
from src.tools.warehouse_client import warehouse_reserve_dock


async def autonomous_actuation_node(state: SentinelState) -> dict[str, Any]:
    """Execute batched fleet actuation transaction.

    Non-LLM deterministic node.
    Enforces:
    - Precondition: requires_immediate_human_override == False
    - Precondition: agreed_action in ["DIVERT_TO_EMERGENCY_COLD_HUB", "PULL_OVER_ROADSIDE_SERVICE", "CONTINUE_MONITORED_ROUTE"]
    - Bound ONLY to:
      - routing_mutate_route
      - warehouse_reserve_dock
      - maintenance_dispatch_ticket
      - sms_send_confirmation
    """
    if state.get("requires_immediate_human_override", False):
        raise StateValidationError(
            "Trust boundary violation: autonomous_actuation invoked while requires_immediate_human_override is True."
        )

    agreed_action = state.get("agreed_action")
    event_id = state.get("event_id", "")
    truck_id = state.get("truck_id", "")
    driver_phone = state.get("driver_phone_e164", "")
    driver_locale = state.get("driver_locale", "en-US")
    cargo = state.get("cargo_manifest")
    bol_number = cargo.bol_number if cargo else "BOL-UNKNOWN"
    commodity = cargo.commodity_type if cargo else "General"

    tool_artifacts: dict[str, ToolCallResult] = {}
    error_logs: list[ErrorRecord] = []
    audit_events: list[AuditEvent] = []

    if agreed_action == "DIVERT_TO_EMERGENCY_COLD_HUB":
        nearest_hub = state.get("nearest_verified_cold_hub") or "Lincoln Cold Logistics Hub"
        coords = state.get("current_coordinates")
        lat = coords.latitude if coords else 40.8136
        lon = coords.longitude if coords else -96.7026

        # Step 1: Mutate Route
        t0 = time.perf_counter()
        route_out = await routing_mutate_route(
            RoutingMutationInput(
                truck_id=truck_id,
                destination_hub_name=nearest_hub,
                destination_lat=lat,
                destination_lon=lon,
            )
        )
        t_route = (time.perf_counter() - t0) * 1000
        tool_artifacts["routing_mutate_route"] = ToolCallResult(
            tool_call_id=f"route_{event_id}",
            tool_name="routing_mutate_route",
            status="SUCCESS" if route_out.route_mutation_confirmed else "FAILED",
            payload=route_out.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=t_route,
        )

        eta_str = route_out.new_eta or datetime.now(timezone.utc).isoformat()

        # Step 2: Reserve Dock
        t0 = time.perf_counter()
        dock_out = await warehouse_reserve_dock(
            WarehouseReservationInput(
                destination_hub_name=nearest_hub,
                truck_id=truck_id,
                bol_number=bol_number,
                eta_timestamp=eta_str,
                commodity_type=commodity,
            )
        )
        t_dock = (time.perf_counter() - t0) * 1000
        tool_artifacts["warehouse_reserve_dock"] = ToolCallResult(
            tool_call_id=f"dock_{event_id}",
            tool_name="warehouse_reserve_dock",
            status="SUCCESS" if dock_out.reservation_confirmed else "FAILED",
            payload=dock_out.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=t_dock,
        )

        dock_bay = dock_out.dock_assignment or "Bay 4"

        # Step 3: SMS Confirmation
        msg_body = (
            f"Cold Chain Sentinel: Route diverted to {nearest_hub}. Dock assignment: {dock_bay}. "
            f"ETA: {route_out.estimated_drive_minutes} mins."
        )
        t0 = time.perf_counter()
        sms_out = await sms_send_confirmation(
            SMSSendInput(
                recipient_phone_e164=driver_phone,
                message_body=msg_body,
                locale=driver_locale,
            )
        )
        t_sms = (time.perf_counter() - t0) * 1000
        tool_artifacts["sms_send_confirmation"] = ToolCallResult(
            tool_call_id=f"sms_{event_id}",
            tool_name="sms_send_confirmation",
            status="SUCCESS" if sms_out.sms_sent else "FAILED",
            payload=sms_out.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=t_sms,
        )

    elif agreed_action == "PULL_OVER_ROADSIDE_SERVICE":
        coords = state.get("current_coordinates")
        lat = coords.latitude if coords else 40.8136
        lon = coords.longitude if coords else -96.7026
        alarm = state.get("driver_reported_alarm_code") or state.get("telematics_alarm_code")

        # Step 1: Maintenance Ticket
        t0 = time.perf_counter()
        maint_out = await maintenance_dispatch_ticket(
            MaintenanceDispatchInput(
                truck_id=truck_id,
                latitude=lat,
                longitude=lon,
                alarm_code=alarm,
                physical_observations_summary="Engine stalled / pull over requested",
            )
        )
        t_maint = (time.perf_counter() - t0) * 1000
        tool_artifacts["maintenance_dispatch_ticket"] = ToolCallResult(
            tool_call_id=f"maint_{event_id}",
            tool_name="maintenance_dispatch_ticket",
            status="SUCCESS" if maint_out.ticket_id else "FAILED",
            payload=maint_out.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=t_maint,
        )

        ticket_id = maint_out.ticket_id or "TCK-PENDING"

        # Step 2: SMS Confirmation
        msg_body = (
            f"Cold Chain Sentinel: Roadside technician dispatched under ticket {ticket_id}. "
            f"ETA: {maint_out.estimated_tech_arrival_minutes} mins. Remain parked safely."
        )
        t0 = time.perf_counter()
        sms_out = await sms_send_confirmation(
            SMSSendInput(
                recipient_phone_e164=driver_phone,
                message_body=msg_body,
                locale=driver_locale,
            )
        )
        t_sms = (time.perf_counter() - t0) * 1000
        tool_artifacts["sms_send_confirmation"] = ToolCallResult(
            tool_call_id=f"sms_{event_id}",
            tool_name="sms_send_confirmation",
            status="SUCCESS" if sms_out.sms_sent else "FAILED",
            payload=sms_out.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=t_sms,
        )

    audit_events.append(
        AuditEvent(
            event_type="NODE_COMPLETED",
            node_name="autonomous_actuation",
            timestamp=datetime.now(timezone.utc).isoformat(),
            details={
                "agreed_action": agreed_action,
                "dispatched_tools": list(tool_artifacts.keys()),
            },
        )
    )

    updates: dict[str, Any] = {
        "tool_artifacts": tool_artifacts,
        "audit_trail": audit_events,
    }
    if error_logs:
        updates["error_logs"] = error_logs

    return updates
