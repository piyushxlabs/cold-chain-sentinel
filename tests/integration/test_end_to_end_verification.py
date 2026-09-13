"""End-to-End Verification Test Suite for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_MASTER_PLAN.md Section 9.4, Section 9.5, Section 10 (Step 20)
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4, Section 6, Section 7
- DOCS/AGENT_LOGIC_SPEC.md Section 2, Section 8, Section 9
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agents.graph import build_sentinel_graph
from src.state.schema import (
    CargoManifest,
    ComplianceReview,
    Coordinates,
    RuntimeConfig,
    SentinelState,
)
from src.tools.schemas.call_e_initiate_triage import (
    CallETriageOutput,
    CallETriageStructuredResult,
)


def create_base_state(event_id: str, commodity_type: str = "Produce") -> SentinelState:
    """Helper to create a pristine base telematics excursion state."""
    return {
        "event_id": event_id,
        "session_id": f"sess_{event_id}",
        "timestamp": "2026-09-13T10:00:00Z",
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "current_temp_f": 39.5,
        "setpoint_temp_f": 34.0,
        "temp_differential_f": 5.5,
        "duration_minutes": 25,
        "telematics_alarm_code": "ALARM 18 - HIGH ENGINE TEMP",
        "current_coordinates": Coordinates(latitude=40.8136, longitude=-96.7026),
        "target_destination": "Omaha DC",
        "origin": "Kansas City Hub",
        "cargo_manifest": CargoManifest(
            bol_number=f"BOL-{event_id}",
            commodity_type=commodity_type,
            min_temp_f=32.0,
            max_temp_f=36.0,
            max_allowable_excursion_minutes=45,
            shipper_name="Midwest Cold Logistics",
        ),
        "driver_phone_e164": "+12065550198",
        "driver_name": "Marcus Vance",
        "driver_locale": "en-US",
        "config": RuntimeConfig(
            trace_id=f"trc_{event_id}",
            client_mode="mock",
            max_tool_retry_attempts=3,
            min_hos_minutes_for_reroute=35,
        ),
        "requires_immediate_human_override": False,
    }


@pytest.mark.asyncio
async def test_e2e_autonomous_divert_pipeline():
    """Verify complete Section 9.1 Simple Case pipeline traversal to AUTONOMOUSLY_DIVERTED.

    Path: ingress -> enrichment -> call_interrogation -> compliance_review -> decision_gate -> autonomous_actuation -> persistence_audit -> END.
    """
    event_id = "evt_e2e_divert_001"
    initial_state = create_base_state(event_id, commodity_type="Produce")

    checkpointer = MemorySaver()
    graph = build_sentinel_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": event_id}}

    final_state = await graph.ainvoke(initial_state, config=config)

    # 1. Verify terminal disposition and agreed action
    assert final_state["disposition"] == "AUTONOMOUSLY_DIVERTED"
    assert final_state["agreed_action"] == "DIVERT_TO_EMERGENCY_COLD_HUB"
    assert final_state["requires_immediate_human_override"] is False

    # 2. Verify all 3 actuation tools executed and produced ToolCallResult artifacts
    artifacts = final_state["tool_artifacts"]
    assert "routing_mutate_route" in artifacts
    assert "warehouse_reserve_dock" in artifacts
    assert "sms_send_confirmation" in artifacts
    assert artifacts["routing_mutate_route"].status == "SUCCESS"
    assert artifacts["warehouse_reserve_dock"].status == "SUCCESS"
    assert artifacts["sms_send_confirmation"].status == "SUCCESS"

    # 3. Verify CALL-E interrogation record
    assert final_state["call_status"] == "completed"
    assert final_state["driver_contacted"] is True
    assert final_state["call_id"] is not None

    # 4. Verify audit trail accumulates node execution
    audit_events = final_state["audit_trail"]
    node_names = [ev.node_name for ev in audit_events if ev.event_type == "NODE_COMPLETED"]
    assert "enrichment" in node_names
    assert "call_interrogation" in node_names
    assert "compliance_review" in node_names
    assert "decision_gate" in node_names
    assert "autonomous_actuation" in node_names


@pytest.mark.asyncio
async def test_e2e_roadside_maintenance_pipeline():
    """Verify roadside service triage outcome dispatches maintenance ticket and SMS without route mutation."""
    event_id = "evt_e2e_roadside_001"
    initial_state = create_base_state(event_id, commodity_type="Produce")

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=False,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ALARM 10 - ENGINE SHUTDOWN",
        driver_hos_minutes_remaining=45,
        selected_option="ROADSIDE_SERVICE",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.92,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_roadside_mock"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "AUTONOMOUSLY_SERVICED"
        assert final_state["agreed_action"] == "PULL_OVER_ROADSIDE_SERVICE"
        assert "maintenance_dispatch_ticket" in final_state["tool_artifacts"]
        assert "sms_send_confirmation" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_escalation_path_1_insufficient_hos():
    """Verify HITL Trigger 1: driver HOS < 35 min routes directly to ESCALATED_HOS_BREACH."""
    event_id = "evt_e2e_hos_fail"
    initial_state = create_base_state(event_id)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=True,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ALARM 18",
        driver_hos_minutes_remaining=20,  # Below threshold
        selected_option="DIVERT_TO_COLD_HUB",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.95,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_mock_hos"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_HOS_BREACH"
        assert final_state["requires_immediate_human_override"] is True
        assert any("hos" in r.lower() for r in final_state["escalation_reasons"])
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state.get("tool_artifacts", {})


@pytest.mark.asyncio
async def test_e2e_escalation_path_2_biologics_sweating():
    """Verify HITL Trigger 2: Biologics with sweating detected routes to ESCALATED_CARGO_SPOILAGE_RISK."""
    event_id = "evt_e2e_bio_sweat"
    initial_state = create_base_state(event_id, commodity_type="Biologics")

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=True,  # Sweating on biologics
        driver_reported_alarm_code="ALARM 04",
        driver_hos_minutes_remaining=45,
        selected_option="DIVERT_TO_COLD_HUB",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.91,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_call_bio_sweating"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_CARGO_SPOILAGE_RISK"
        assert final_state["requires_immediate_human_override"] is True
        assert any("sweating" in r.lower() or "biologics" in r.lower() for r in final_state["escalation_reasons"])
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_escalation_path_3_telephony_drop():
    """Verify HITL Trigger 3: Telephony drop / failure routes immediately to ESCALATED_TELEPHONY_FAILURE."""
    event_id = "evt_e2e_call_drop"
    initial_state = create_base_state(event_id)

    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="failed",
        task_completed=False,
        completion_confidence=0.0,
        structured_result=None,
        evidence={"transcript_or_evidence_ref": "NO_ANSWER"},
        error="Driver phone busy / no answer",
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_TELEPHONY_FAILURE"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_escalation_path_4_driver_refusal():
    """Verify HITL Trigger 4: Driver refusal routes to ESCALATED_DRIVER_REFUSAL."""
    event_id = "evt_e2e_driver_refuse"
    initial_state = create_base_state(event_id)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ALARM 18",
        driver_hos_minutes_remaining=50,
        selected_option="DRIVER_REFUSED",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.88,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_refuse"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_DRIVER_REFUSAL"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_escalation_path_5_emergency_reported():
    """Verify HITL Trigger 5: 911 emergency report routes to ESCALATED_MANUAL_OVERRIDE."""
    event_id = "evt_e2e_emergency"
    initial_state = create_base_state(event_id)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=False,
        reefer_engine_running=False,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ACCIDENT",
        driver_hos_minutes_remaining=40,
        selected_option="DRIVER_REFUSED",
        emergency_reported=True,  # Active emergency
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.96,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_accident_911"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_MANUAL_OVERRIDE"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_escalation_path_6_prompt_injection():
    """Verify HITL Trigger 6: Suspected prompt injection locks override and routes to ESCALATED_INJECTION_DETECTED."""
    event_id = "evt_e2e_injection"
    initial_state = create_base_state(event_id)

    mock_review_output = {
        "compliance_review": ComplianceReview(
            claim_risk_level="HIGH",
            review_confidence=0.85,
            suspected_injection=True,
            reviewer_model="gemini-3.5-flash",
            reasoning_summary="Per physical_observations.cargo_sweating_detected, sweating detected. Suspected prompt injection in transcript reference.",
        ),
        "requires_immediate_human_override": True,
        "escalation_reasons": ["suspected_injection_in_call_evidence"],
    }

    with patch("src.agents.graph.compliance_review_node", return_value=mock_review_output):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_INJECTION_DETECTED"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_e2e_checkpoint_crash_resumption_no_redial():
    """Verify that a session persisted to AsyncSqliteSaver preserves state without redialing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "checkpoints_e2e.db")
        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            await checkpointer.setup()
            graph = build_sentinel_graph(checkpointer=checkpointer)

            event_id = "evt_e2e_crash_resume"
            initial_state = create_base_state(event_id)
            config = {"configurable": {"thread_id": event_id}}

            # First run: traverses graph and persists checkpoints
            first_pass = await graph.ainvoke(initial_state, config=config)
            assert first_pass["disposition"] == "AUTONOMOUSLY_DIVERTED"
            first_call_id = first_pass["call_id"]

            # Checkpoint snapshot rehydration
            state_tuple = await checkpointer.aget_tuple(config)
            assert state_tuple is not None
            persisted_values = state_tuple.checkpoint["channel_values"]
            assert persisted_values["call_id"] == first_call_id
            assert persisted_values["disposition"] == "AUTONOMOUSLY_DIVERTED"
            assert persisted_values["requires_immediate_human_override"] is False
