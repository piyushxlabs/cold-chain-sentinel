"""End-to-End Reasoning Loop Integration Test.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Section 9.1 & Step 12.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agents.graph import build_sentinel_graph
from src.state.schema import CargoManifest, Coordinates, RuntimeConfig, SentinelState


@pytest.mark.asyncio
async def test_simple_case_end_to_end_reasoning_loop() -> None:
    """Execute full Section 9.1 Simple Case from ingress to persistence_audit with MemorySaver.

    Expected Path:
    ingress -> enrichment -> call_interrogation -> compliance_review ->
    decision_gate -> autonomous_actuation -> persistence_audit -> END
    """
    checkpointer = MemorySaver()
    app = build_sentinel_graph(checkpointer=checkpointer)

    event_id = "evt_reefer_99482_exc"
    cargo = CargoManifest(
        bol_number="BOL-9901",
        commodity_type="Produce",
        min_temp_f=35.0,
        max_temp_f=42.0,
        max_allowable_excursion_minutes=60,
        shipper_name="FreshHarvest Logistics",
    )
    coords = Coordinates(latitude=40.8136, longitude=-96.7026)
    config = RuntimeConfig(
        trace_id=f"trc_{event_id}",
        client_mode="mock",
        max_tool_retry_attempts=3,
        min_hos_minutes_for_reroute=35,
    )

    initial_state: SentinelState = {
        "event_id": event_id,
        "session_id": f"ses_{event_id}",
        "truck_id": "TRK-8812",
        "trailer_id": "TRL-904",
        "current_temp_f": 45.2,
        "setpoint_temp_f": 38.0,
        "temp_differential_f": 7.2,
        "duration_minutes": 22,
        "telematics_alarm_code": "ALARM 18 - HIGH ENGINE TEMP",
        "current_coordinates": coords,
        "target_destination": "Lincoln Logistics Hub",
        "origin": "Omaha Cold Center",
        "cargo_manifest": cargo,
        "driver_phone_e164": "+12065550198",
        "driver_name": "Marcus Vance",
        "driver_locale": "en-US",
        "config": config,
    }

    # Execute StateGraph end-to-end
    config_dict = {"configurable": {"thread_id": event_id}}
    final_state = await app.ainvoke(initial_state, config_dict)

    # 1. State Invariant & Enrichment Assertions
    assert final_state["event_id"] == event_id
    assert final_state["truck_id"] == "TRK-8812"
    assert final_state["tms_verified"] is True
    assert final_state["eld_hos_minutes_at_dispatch"] == 52

    # 2. CALL-E Driver Interrogation Assertions
    assert final_state["call_status"] == "completed"
    assert final_state["driver_contacted"] is True
    assert final_state["driver_hos_minutes_remaining"] == 45
    assert final_state["physical_observations"] is not None
    assert final_state["physical_observations"].air_bulkhead_obstructed is True
    assert final_state["call_evidence"] is not None
    assert final_state["call_evidence"].task_completed is True

    # 3. Compliance Review Assertions
    assert final_state["compliance_review"] is not None
    assert final_state["compliance_review"].claim_risk_level in ["LOW", "MODERATE", "HIGH"]
    assert final_state["compliance_review"].suspected_injection is False

    # 4. Deterministic Decision Gate Assertions
    assert final_state["agreed_action"] == "DIVERT_TO_EMERGENCY_COLD_HUB"
    assert final_state["disposition"] == "AUTONOMOUSLY_DIVERTED"
    assert final_state["requires_immediate_human_override"] is False

    # 5. Autonomous Actuation Assertions
    tool_artifacts = final_state.get("tool_artifacts", {})
    assert "tms_lookup_driver_and_load" in tool_artifacts
    assert "eld_lookup_hos_minutes" in tool_artifacts
    assert "call_e_initiate_triage" in tool_artifacts
    assert "routing_mutate_route" in tool_artifacts
    assert "warehouse_reserve_dock" in tool_artifacts
    assert "sms_send_confirmation" in tool_artifacts

    assert tool_artifacts["routing_mutate_route"].status == "SUCCESS"
    assert tool_artifacts["warehouse_reserve_dock"].status == "SUCCESS"
    assert tool_artifacts["sms_send_confirmation"].status == "SUCCESS"

    # 6. Persistence & Audit Trail Assertions
    assert final_state["execution_timestamp"] is not None
    audit_trail = final_state.get("audit_trail", [])
    node_names_in_audit = [ev.node_name for ev in audit_trail]
    assert "ingress" in node_names_in_audit
    assert "enrichment" in node_names_in_audit
    assert "call_interrogation" in node_names_in_audit
    assert "compliance_review" in node_names_in_audit
    assert "decision_gate" in node_names_in_audit
    assert "autonomous_actuation" in node_names_in_audit
    assert "persistence_audit" in node_names_in_audit


@pytest.mark.asyncio
async def test_reasoning_loop_with_sqlite_checkpointer() -> None:
    """Verify reasoning loop persists state across nodes using AsyncSqliteSaver."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "checkpoints.db")
        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            await checkpointer.setup()
            app = build_sentinel_graph(checkpointer=checkpointer)

            event_id = "evt_sqlite_test_001"
            cargo = CargoManifest(
                bol_number="BOL-7711",
                commodity_type="Dairy",
                min_temp_f=34.0,
                max_temp_f=40.0,
                max_allowable_excursion_minutes=45,
                shipper_name="Midwest Dairy Express",
            )
            coords = Coordinates(latitude=41.2565, longitude=-95.9345)
            config = RuntimeConfig(
                trace_id=f"trc_{event_id}",
                client_mode="mock",
                max_tool_retry_attempts=3,
                min_hos_minutes_for_reroute=35,
            )

            initial_state: SentinelState = {
                "event_id": event_id,
                "session_id": f"ses_{event_id}",
                "truck_id": "TRK-4421",
                "trailer_id": "TRL-882",
                "current_temp_f": 46.5,
                "setpoint_temp_f": 36.0,
                "temp_differential_f": 10.5,
                "duration_minutes": 30,
                "telematics_alarm_code": "ALARM 12",
                "current_coordinates": coords,
                "target_destination": "Lincoln Logistics Hub",
                "origin": "Des Moines Center",
                "cargo_manifest": cargo,
                "driver_phone_e164": "+12065550198",
                "driver_name": "Marcus Vance",
                "driver_locale": "en-US",
                "config": config,
            }

            config_dict = {"configurable": {"thread_id": event_id}}
            final_state = await app.ainvoke(initial_state, config_dict)

            assert final_state["event_id"] == event_id
            assert final_state["disposition"] == "AUTONOMOUSLY_DIVERTED"
            assert final_state["execution_timestamp"] is not None

            # Rehydrate from checkpoint to verify persistence
            state_tuple = await checkpointer.aget_tuple(config_dict)
            assert state_tuple is not None
            persisted_state = state_tuple.checkpoint["channel_values"]
            assert persisted_state["event_id"] == event_id
            assert persisted_state["tms_verified"] is True
            assert persisted_state["disposition"] == "AUTONOMOUSLY_DIVERTED"
