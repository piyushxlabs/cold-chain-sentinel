"""Negative Safety Guardrail & Human-in-the-Loop (HITL) Integration Tests.

Authoritative specifications:
- DOCS/AGENT_MASTER_PLAN.md Section 8 & Step 13
- DOCS/AGENT_LOGIC_SPEC.md Section 8 & Section 10
- RULE: code-level-verification-over-model-discretion.md
- RULE: ui-non-goals-interface-boundaries.md
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.agents.autonomous_actuation import autonomous_actuation_node
from src.agents.graph import build_sentinel_graph
from src.state.exceptions import StateValidationError
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


def create_base_state(event_id: str, cargo: CargoManifest) -> SentinelState:
    coords = Coordinates(latitude=40.8136, longitude=-96.7026)
    config = RuntimeConfig(
        trace_id=f"trc_{event_id}",
        client_mode="mock",
        max_tool_retry_attempts=3,
        min_hos_minutes_for_reroute=35,
    )
    return {
        "event_id": event_id,
        "session_id": f"ses_{event_id}",
        "truck_id": "TRK-8812",
        "trailer_id": "TRL-904",
        "current_temp_f": 45.2,
        "setpoint_temp_f": 38.0,
        "temp_differential_f": 7.2,
        "duration_minutes": 22,
        "telematics_alarm_code": "ALARM 18",
        "current_coordinates": coords,
        "target_destination": "Lincoln Logistics Hub",
        "origin": "Omaha Cold Center",
        "cargo_manifest": cargo,
        "driver_phone_e164": "+12065550198",
        "driver_name": "Marcus Vance",
        "driver_locale": "en-US",
        "config": config,
    }


@pytest.mark.asyncio
async def test_hitl_trigger_1_insufficient_hos() -> None:
    """Trigger 1: Driver HOS < 35 min must escalate to ESCALATED_HOS_BREACH without route mutation."""
    event_id = "evt_hitl_hos_001"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Produce",
        min_temp_f=35.0,
        max_temp_f=42.0,
        max_allowable_excursion_minutes=60,
        shipper_name="FreshHarvest Logistics",
    )
    base_state = create_base_state(event_id, cargo)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=True,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ALARM 18",
        driver_hos_minutes_remaining=20,  # Below 35 min threshold
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
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_HOS_BREACH"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]
        assert "warehouse_reserve_dock" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_hitl_trigger_2_biologics_cargo_sweating() -> None:
    """Trigger 2: Cargo sweating on Biologics cargo must escalate to ESCALATED_CARGO_SPOILAGE_RISK."""
    event_id = "evt_hitl_biologics_001"
    cargo = CargoManifest(
        bol_number="BOL-BIO-441",
        commodity_type="Biologics",
        min_temp_f=36.0,
        max_temp_f=40.0,
        max_allowable_excursion_minutes=30,
        shipper_name="BioVax Pharma",
    )
    base_state = create_base_state(event_id, cargo)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=True,  # Sweating detected on biologics load!
        driver_reported_alarm_code="ALARM 12",
        driver_hos_minutes_remaining=55,
        selected_option="DIVERT_TO_COLD_HUB",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.92,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_mock_sweating"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_CARGO_SPOILAGE_RISK"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_hitl_trigger_3_telephony_drop() -> None:
    """Trigger 3: Call dropped / no-answer must escalate immediately with Zero-Redial."""
    event_id = "evt_hitl_call_drop_001"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Produce",
        min_temp_f=35.0,
        max_temp_f=42.0,
        max_allowable_excursion_minutes=60,
        shipper_name="FreshHarvest Logistics",
    )
    base_state = create_base_state(event_id, cargo)

    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="no_answer",
        task_completed=False,
        completion_confidence=0.0,
        error="Driver did not answer telephony call",
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_TELEPHONY_FAILURE"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_hitl_trigger_4_driver_refusal() -> None:
    """Trigger 4: Driver refusal must route to ESCALATED_DRIVER_REFUSAL."""
    event_id = "evt_hitl_refusal_001"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Dairy",
        min_temp_f=34.0,
        max_temp_f=40.0,
        max_allowable_excursion_minutes=60,
        shipper_name="Dairy Best",
    )
    base_state = create_base_state(event_id, cargo)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code=None,
        driver_hos_minutes_remaining=60,
        selected_option="DRIVER_REFUSED",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.91,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_mock_refusal"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_DRIVER_REFUSAL"
        assert final_state["agreed_action"] == "DRIVER_REFUSED"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_hitl_trigger_5_emergency_reported() -> None:
    """Trigger 5: Active emergency reported on call must lock override to ESCALATED_MANUAL_OVERRIDE."""
    event_id = "evt_hitl_emergency_001"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Meat",
        min_temp_f=30.0,
        max_temp_f=36.0,
        max_allowable_excursion_minutes=60,
        shipper_name="Prime Meats Inc",
    )
    base_state = create_base_state(event_id, cargo)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=False,
        reefer_engine_running=False,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code=None,
        driver_hos_minutes_remaining=60,
        selected_option="DIVERT_TO_COLD_HUB",
        emergency_reported=True,  # Active emergency reported!
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.90,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_mock_emergency"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_MANUAL_OVERRIDE"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_hitl_trigger_6_prompt_injection_flagged() -> None:
    """Trigger 6: Suspected prompt injection in driver evidence must escalate to ESCALATED_INJECTION_DETECTED."""
    event_id = "evt_hitl_injection_001"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Produce",
        min_temp_f=35.0,
        max_temp_f=42.0,
        max_allowable_excursion_minutes=60,
        shipper_name="FreshHarvest Logistics",
    )
    base_state = create_base_state(event_id, cargo)

    mock_compliance = {
        "compliance_review": ComplianceReview(
            claim_risk_level="HIGH",
            review_confidence=0.90,
            suspected_injection=True,
            reviewer_model="gemini-3.5-flash-test",
            reasoning_summary="Per call_evidence.transcript_or_evidence_ref, driver utterance contains injection pattern 'ignore previous instructions'.",
            injection_evidence_note="Driver attempted prompt redirection",
        ),
        "requires_immediate_human_override": True,
        "escalation_reasons": ["suspected_injection_in_call_evidence"],
    }

    with patch("src.agents.graph.compliance_review_node", return_value=mock_compliance):
        app = build_sentinel_graph(checkpointer=MemorySaver())
        final_state = await app.ainvoke(base_state, {"configurable": {"thread_id": event_id}})

        assert final_state["disposition"] == "ESCALATED_INJECTION_DETECTED"
        assert final_state["requires_immediate_human_override"] is True
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_trust_boundary_direct_invocation_rejected() -> None:
    """Verify autonomous_actuation_node directly rejects invocation if override is active."""
    invalid_state: SentinelState = {
        "event_id": "evt_invalid_001",
        "requires_immediate_human_override": True,
        "agreed_action": "DIVERT_TO_EMERGENCY_COLD_HUB",
    }
    with pytest.raises(StateValidationError, match="Trust boundary violation"):
        await autonomous_actuation_node(invalid_state)


def test_prohibitions_structural_enforcement() -> None:
    """Verify prohibitions (no vehicle controls, no financial claims fields)."""
    from src.state.schema import SentinelState

    state_annotations = SentinelState.__annotations__
    # Prohibit financial claim values in shared state
    prohibited_fields = ["claim_amount", "settlement_value", "freight_cost", "detention_pay"]
    for field in prohibited_fields:
        assert field not in state_annotations, f"Prohibited field '{field}' found in SentinelState!"
