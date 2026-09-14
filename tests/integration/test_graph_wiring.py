"""Integration test for LangGraph 8-node StateGraph topology and conditional wiring.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Step 11.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.agents.autonomous_actuation import autonomous_actuation_node
from src.agents.call_interrogation import call_interrogation_node
from src.agents.decision_gate import decision_gate_node
from src.agents.enrichment import enrichment_node
from src.agents.escalation_failure import escalation_failure_node
from src.agents.graph import (
    build_sentinel_graph,
    create_sentinel_graph,
    route_after_call,
    route_after_decision_gate,
    route_after_enrichment,
)
from src.agents.ingress import ingress_node
from src.agents.persistence_audit import persistence_audit_node
from src.state.schema import CargoManifest, Coordinates, RuntimeConfig, SentinelState


def test_graph_has_all_eight_nodes() -> None:
    """Verify graph contains exactly the 8 specification nodes."""
    workflow = create_sentinel_graph()
    expected_nodes = {
        "ingress",
        "enrichment",
        "call_interrogation",
        "compliance_review",
        "decision_gate",
        "autonomous_actuation",
        "escalation_failure",
        "persistence_audit",
    }
    assert set(workflow.nodes.keys()) == expected_nodes


def test_graph_compilation_with_checkpointer() -> None:
    """Verify StateGraph compiles cleanly with MemorySaver."""
    checkpointer = MemorySaver()
    app = build_sentinel_graph(checkpointer=checkpointer)
    assert app is not None
    assert hasattr(app, "invoke")
    assert hasattr(app, "ainvoke")


def test_route_after_enrichment_logic() -> None:
    """Test conditional branching after enrichment node."""
    state_valid: SentinelState = {
        "tms_verified": True,
        "requires_immediate_human_override": False,
    }
    assert route_after_enrichment(state_valid) == "call_interrogation"

    state_tms_failed: SentinelState = {
        "tms_verified": False,
        "requires_immediate_human_override": False,
    }
    assert route_after_enrichment(state_tms_failed) == "escalation_failure"

    state_override: SentinelState = {
        "tms_verified": True,
        "requires_immediate_human_override": True,
    }
    assert route_after_enrichment(state_override) == "escalation_failure"


def test_route_after_call_logic() -> None:
    """Test conditional branching after CALL-E call interrogation node."""
    state_completed: SentinelState = {
        "call_status": "completed",
    }
    assert route_after_call(state_completed) == "compliance_review"

    state_no_answer: SentinelState = {
        "call_status": "no_answer",
    }
    assert route_after_call(state_no_answer) == "escalation_failure"

    state_failed: SentinelState = {
        "call_status": "failed",
    }
    assert route_after_call(state_failed) == "escalation_failure"


def test_route_after_decision_gate_logic() -> None:
    """Test conditional branching after Decision Gate evaluation."""
    state_divert: SentinelState = {
        "agreed_action": "DIVERT_TO_EMERGENCY_COLD_HUB",
        "requires_immediate_human_override": False,
    }
    assert route_after_decision_gate(state_divert) == "autonomous_actuation"

    state_maint: SentinelState = {
        "agreed_action": "PULL_OVER_ROADSIDE_SERVICE",
        "requires_immediate_human_override": False,
    }
    assert route_after_decision_gate(state_maint) == "autonomous_actuation"

    state_escalate: SentinelState = {
        "agreed_action": "ESCALATE_TO_HUMAN_DISPATCH",
        "requires_immediate_human_override": True,
    }
    assert route_after_decision_gate(state_escalate) == "escalation_failure"

    state_refused: SentinelState = {
        "agreed_action": "DRIVER_REFUSED",
        "requires_immediate_human_override": True,
    }
    assert route_after_decision_gate(state_refused) == "escalation_failure"


@pytest.mark.asyncio
async def test_node_execution_sequence() -> None:
    """Test individual node functions with typed states."""
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Biologics",
        min_temp_f=35.0,
        max_temp_f=42.0,
        max_allowable_excursion_minutes=60,
        shipper_name="BioPharma Global",
    )
    coords = Coordinates(latitude=40.8136, longitude=-96.7026)
    config = RuntimeConfig(
        trace_id="trc_test_001",
        client_mode="mock",
        max_tool_retry_attempts=3,
        min_hos_minutes_for_reroute=35,
    )

    base_state: SentinelState = {
        "event_id": "evt_test_001",
        "session_id": "ses_test_001",
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

    # Test Ingress
    ingress_res = await ingress_node(base_state)
    assert "audit_trail" in ingress_res

    # Test Enrichment
    enrichment_res = await enrichment_node(base_state)
    assert enrichment_res["tms_verified"] is True
    assert enrichment_res["eld_hos_minutes_at_dispatch"] == 52

    # Test Call Interrogation
    call_state = {**base_state, **enrichment_res}
    call_res = await call_interrogation_node(call_state)
    assert call_res["call_status"] == "completed"
    assert call_res["driver_contacted"] is True

    # Test Decision Gate
    decision_state = {**call_state, **call_res}
    decision_res = await decision_gate_node(decision_state)
    assert decision_res["agreed_action"] in [
        "DIVERT_TO_EMERGENCY_COLD_HUB",
        "PULL_OVER_ROADSIDE_SERVICE",
        "CONTINUE_MONITORED_ROUTE",
        "ESCALATE_TO_HUMAN_DISPATCH",
    ]

    # Test Autonomous Actuation
    actuation_state = {**decision_state, **decision_res, "agreed_action": "DIVERT_TO_EMERGENCY_COLD_HUB", "requires_immediate_human_override": False}
    actuation_res = await autonomous_actuation_node(actuation_state)
    assert "routing_mutate_route" in actuation_res["tool_artifacts"]
    assert "warehouse_reserve_dock" in actuation_res["tool_artifacts"]
    assert "sms_send_confirmation" in actuation_res["tool_artifacts"]

    # Test Escalation Failure
    escalation_state = {**decision_state, "escalation_reasons": ["test_escalation"]}
    escalation_res = await escalation_failure_node(escalation_state)
    assert escalation_res["requires_immediate_human_override"] is True
    assert "ops_alert_escalate" in escalation_res["tool_artifacts"]

    # Test Persistence Audit
    persistence_res = await persistence_audit_node(actuation_state)
    assert persistence_res["execution_timestamp"] is not None


@pytest.mark.asyncio
async def test_decision_gate_missing_hos_string_and_deduplication():
    """Verify decision_gate formats missing HOS data cleanly and deduplicates reasons."""
    from src.agents.decision_gate import decision_gate_node

    state = {
        "event_id": "evt_test_missing_hos",
        "driver_hos_minutes_remaining": None,  # Missing HOS
        "escalation_reasons": ["call_status_failed"],  # Existing reason
        "tool_artifacts": {},
    }

    res = await decision_gate_node(state)  # type: ignore
    assert res["disposition"] == "ESCALATED_HOS_BREACH"
    assert "escalation_reasons" in res
    # Must format as missing_hos_data, never Nonem_lt_35m
    assert "insufficient_hos_for_reroute_missing_hos_data" in res["escalation_reasons"]
    assert not any("Nonem" in r for r in res["escalation_reasons"])
    # Must not duplicate call_status_failed
    assert res["escalation_reasons"].count("call_status_failed") == 0
