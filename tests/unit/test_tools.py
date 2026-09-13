"""Unit tests for all 8 Cold Chain Sentinel tools.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Section 5 & Section 9.1.
"""

import pytest

from src.state.exceptions import StateValidationError
from src.tools import (
    call_e_initiate_triage,
    eld_lookup_hos_minutes,
    maintenance_dispatch_ticket,
    ops_alert_escalate,
    routing_mutate_route,
    sms_send_confirmation,
    tms_lookup_driver_and_load,
    warehouse_reserve_dock,
)
from src.tools.call_e_client import extract_confidence_score, format_calle_task
from src.tools.schemas import (
    CallETriageInput,
    ELDLookupInput,
    MaintenanceDispatchInput,
    OpsAlertInput,
    RoutingMutationInput,
    SMSSendInput,
    TMSLookupInput,
    WarehouseReservationInput,
)


def test_call_e_task_formatting_and_confidence():
    """Verify CALL-E task prefix requirement and defensive confidence extraction."""
    task = format_calle_task("+12065550198", "check reefer bulkhead")
    assert task == "Call +12065550198 and check reefer bulkhead"

    # Scalar float confidence
    assert extract_confidence_score(0.95) == 0.95
    # Dict confidence format
    assert extract_confidence_score({"score": 0.88, "label": "high"}) == 0.88
    # Boundary clamp
    assert extract_confidence_score(1.5) == 1.0
    assert extract_confidence_score(-0.2) == 0.0


@pytest.mark.asyncio
async def test_call_e_initiate_triage_tool():
    """Verify call_e_initiate_triage tool execution with Mock client."""
    input_data = CallETriageInput(
        recipient_phone_e164="+12065550198",
        driver_locale="en-US",
        task_instructions="Interrogate driver regarding reefer temperature alarm.",
        result_schema={},
    )
    output = await call_e_initiate_triage(input_data)

    assert output.status == "completed"
    assert output.task_completed is True
    assert output.completion_confidence == 0.94
    assert output.structured_result is not None
    assert output.structured_result.air_bulkhead_obstructed is True
    assert output.structured_result.driver_hos_minutes_remaining == 45


@pytest.mark.asyncio
async def test_call_e_invalid_phone_rejected():
    """Verify non-E.164 phone number is rejected immediately."""
    with pytest.raises(StateValidationError):
        await call_e_initiate_triage(
            CallETriageInput(
                recipient_phone_e164="555-0198",  # Invalid
                task_instructions="Check reefer",
                result_schema={},
            )
        )


@pytest.mark.asyncio
async def test_tms_lookup_tool():
    """Verify tms_lookup_driver_and_load execution."""
    input_data = TMSLookupInput(
        truck_id="TRK-880",
        trailer_id="TRL-992",
        event_id="evt_test_001",
    )
    output = await tms_lookup_driver_and_load(input_data)

    assert output.tms_verified is True
    assert output.bol_number == "BOL-9901"
    assert output.nearest_verified_cold_hub.name == "Lincoln Cold Logistics Hub"
    assert output.nearest_verified_cold_hub.lat == 40.8136


@pytest.mark.asyncio
async def test_eld_lookup_tool():
    """Verify eld_lookup_hos_minutes execution."""
    input_data = ELDLookupInput(
        truck_id="TRK-880",
        driver_phone_e164="+12065550198",
    )
    output = await eld_lookup_hos_minutes(input_data)

    assert output.hos_minutes_remaining == 52
    assert output.as_of_timestamp is not None


@pytest.mark.asyncio
async def test_routing_mutate_route_tool():
    """Verify routing_mutate_route execution."""
    input_data = RoutingMutationInput(
        truck_id="TRK-880",
        destination_hub_name="Lincoln Cold Logistics Hub",
        destination_lat=40.8136,
        destination_lon=-96.7026,
    )
    output = await routing_mutate_route(input_data)

    assert output.route_mutation_confirmed is True
    assert output.new_route_id == "RTE-DIVERT-88910"
    assert output.estimated_drive_minutes == 18


@pytest.mark.asyncio
async def test_warehouse_reserve_dock_tool():
    """Verify warehouse_reserve_dock execution."""
    input_data = WarehouseReservationInput(
        destination_hub_name="Lincoln Cold Logistics Hub",
        truck_id="TRK-880",
        bol_number="BOL-9901",
        eta_timestamp="2026-09-13T12:00:00Z",
        commodity_type="Biologics",
    )
    output = await warehouse_reserve_dock(input_data)

    assert output.reservation_confirmed is True
    assert "Dock Bay 4" in output.dock_assignment
    assert output.reservation_id == "RES-WH-44091"


@pytest.mark.asyncio
async def test_maintenance_dispatch_ticket_tool():
    """Verify maintenance_dispatch_ticket execution."""
    input_data = MaintenanceDispatchInput(
        truck_id="TRK-880",
        latitude=40.8136,
        longitude=-96.7026,
        alarm_code="ALARM 18",
        physical_observations_summary="Engine shutdown, visual smoke",
    )
    output = await maintenance_dispatch_ticket(input_data)

    assert output.ticket_id == "TCK-ROADSIDE-7712"
    assert output.dispatch_status == "DISPATCHED_MOBILE_UNIT"


@pytest.mark.asyncio
async def test_sms_send_confirmation_tool():
    """Verify sms_send_confirmation execution."""
    input_data = SMSSendInput(
        recipient_phone_e164="+12065550198",
        message_body="Rerouted to Lincoln Cold Hub, Dock 4 reserved.",
    )
    output = await sms_send_confirmation(input_data)

    assert output.sms_sent is True
    assert output.provider_message_id == "msg_carrier_sms_991823"


@pytest.mark.asyncio
async def test_ops_alert_escalate_tool():
    """Verify ops_alert_escalate execution."""
    input_data = OpsAlertInput(
        event_id="evt_test_001",
        escalation_reasons=["HOS minutes remaining (20) below threshold (35)"],
        severity_level="P0_CRITICAL",
        state_summary={"truck_id": "TRK-880", "commodity": "Biologics"},
    )
    output = await ops_alert_escalate(input_data)

    assert output.delivered is True
    assert output.alert_id == "alrt_ops_p0_88921"
    assert output.channel == "OPS_PAGER_P0"
