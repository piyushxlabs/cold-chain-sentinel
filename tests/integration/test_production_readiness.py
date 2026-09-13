"""
Production Readiness Verification Suite (Step 21)
=================================================
Validates production cutover, test API endpoint preservation, standalone CALL-E
skill PR target isolation, and Section 9.5 failure simulations.
"""

import ast
import importlib.util
import os
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

# Dynamically import standalone triage skill (hyphenated folder name)
_triage_path = Path("skills/cold-chain-reefer-triage/triage.py").resolve()
_spec = importlib.util.spec_from_file_location("cold_chain_reefer_triage", _triage_path)
_triage_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_triage_mod)

StandaloneCallETriageOutput = _triage_mod.CallETriageOutput
StandaloneCallETriageStructuredResult = _triage_mod.CallETriageStructuredResult
initiate_reefer_triage = _triage_mod.initiate_reefer_triage

from src.state.checkpointing import get_checkpointer, get_async_checkpointer
from src.agents.graph import build_sentinel_graph
from src.state.schema import CargoManifest, RuntimeConfig, SentinelState
from src.tools.schemas.call_e_initiate_triage import CallETriageOutput, CallETriageStructuredResult
from src.main import app
from httpx import AsyncClient, ASGITransport
from langgraph.checkpoint.memory import MemorySaver


# ==============================================================================
# 1. Standalone Skill Package Isolation Tests
# ==============================================================================

def test_skill_boundary_isolation_zero_framework_imports():
    """
    Asserts that `skills/cold-chain-reefer-triage/triage.py` has ZERO imports
    of backend frameworks (FastAPI, LangGraph, Langfuse, OpenTelemetry, or internal src.*).
    """
    skill_file = Path("skills/cold-chain-reefer-triage/triage.py")
    assert skill_file.exists(), "skills/cold-chain-reefer-triage/triage.py must exist"

    with open(skill_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(skill_file))

    disallowed_roots = {
        "fastapi",
        "langgraph",
        "langchain",
        "opentelemetry",
        "langfuse",
        "uvicorn",
        "httpx",
        "src",
        "psycopg",
        "aiosqlite",
    }

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])

    leaked = imported_modules.intersection(disallowed_roots)
    assert not leaked, f"Boundary violation: Standalone skill imports backend frameworks: {leaked}"


def test_skill_standalone_execution():
    """
    Tests standalone `initiate_reefer_triage` function with mock CALL-E SDK client.
    """
    mock_calle = MagicMock()
    mock_response = MagicMock()
    mock_response.id = "calle_skill_test_001"
    mock_response.status = "completed"
    mock_response.completion_confidence = {"score": 0.95, "label": "HIGH"}
    mock_response.structured_result = {
        "driver_verified_safe_location": True,
        "reefer_engine_running": True,
        "air_bulkhead_obstructed": False,
        "cargo_sweating_detected": False,
        "driver_reported_alarm_code": "ALARM 18",
        "driver_hos_minutes_remaining": 50,
        "selected_option": "DIVERT_TO_COLD_HUB",
        "emergency_reported": False,
    }
    mock_response.evidence = {"transcript": "Call completed successfully."}
    mock_calle.calls.create_and_wait.return_value = mock_response

    output = initiate_reefer_triage(
        client=mock_calle,
        driver_phone="+12065550198",
        driver_name="Elena Rostova",
        truck_id="TRK-100",
        trailer_id="TRL-200",
        current_temp_f=38.0,
        setpoint_temp_f=34.0,
        nearest_cold_hub_name="Test Cold Hub",
        nearest_cold_hub_eta_minutes=15,
    )

    assert output.task_completed is True
    assert output.status == "completed"
    assert output.completion_confidence == 0.95
    assert output.structured_result is not None
    assert output.structured_result.selected_option == "DIVERT_TO_COLD_HUB"
    assert output.structured_result.driver_hos_minutes_remaining == 50

    # Verify task prompt started with Call + phone
    call_args = mock_calle.calls.create_and_wait.call_args[1]
    assert call_args["task"].startswith("Call +12065550198 and speak with driver Elena Rostova")


# ==============================================================================
# 2. Live Environment & Endpoint Preservation Tests
# ==============================================================================

def test_live_calle_client_test_endpoint_configuration():
    """
    Validates that live CalleClient resolves the designated test endpoint
    to preserve live calling credits during test/staging verification.
    """
    with patch.dict(os.environ, {
        "CLIENT_MODE": "live",
        "CALLE_API_KEY": "test_calle_key_123",
        "CALLE_BASE_URL": "https://test-api.heycall-e.com",
    }):
        from calle import CalleClient
        client = CalleClient(
            api_key=os.environ["CALLE_API_KEY"],
            base_url=os.environ["CALLE_BASE_URL"],
        )
        assert client is not None
        assert str(client._client.base_url) == "https://test-api.heycall-e.com"


def test_postgres_checkpoint_backend_missing_conn_str():
    """
    Validates that CHECKPOINT_BACKEND=postgres raises ValueError if POSTGRES_CONNECTION_STRING is missing.
    """
    with patch.dict(os.environ, {
        "CHECKPOINT_BACKEND": "postgres",
    }, clear=False):
        os.environ.pop("POSTGRES_CONNECTION_STRING", None)
        with pytest.raises(ValueError, match="POSTGRES_CONNECTION_STRING is required"):
            with get_checkpointer():
                pass


def test_security_and_env_hygiene():
    """
    Validates that .env is ignored in git and .env.example contains all required vars.
    """
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists()
    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    assert ".env" in gitignore_content

    example_env_path = Path(".env.example")
    assert example_env_path.exists()
    example_env = example_env_path.read_text(encoding="utf-8")

    required_vars = [
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_FALLBACK_MODEL",
        "CALLE_API_KEY",
        "CALLE_BASE_URL",
        "CLIENT_MODE",
        "CHECKPOINT_BACKEND",
        "POSTGRES_CONNECTION_STRING",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    ]
    for var in required_vars:
        assert var in example_env, f"Missing required env var in .env.example: {var}"


# ==============================================================================
# 3. Section 9.5 Failure Simulations
# ==============================================================================

def create_base_state(event_id: str, commodity_type: str = "Produce") -> SentinelState:
    """Helper to create a pristine base telematics excursion state."""
    return {
        "event_id": event_id,
        "session_id": f"sess_{event_id}",
        "timestamp": "2026-09-13T10:00:00Z",
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "current_temp_f": 38.5,
        "setpoint_temp_f": 34.0,
        "telematics_alarm_code": "ALARM 18 - HIGH ENGINE TEMP",
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
async def test_simulation_1_call_no_answer_immediate_escalation():
    """
    Simulation 1: call_e_initiate_triage returns NO_ANSWER.
    Asserts immediate escalation to escalation_failure with 0 retries and ops_alert_escalate fired.
    """
    event_id = "sim_1_no_ans"
    initial_state = create_base_state(event_id)

    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="no_answer",
        task_completed=False,
        completion_confidence=0.0,
        structured_result=None,
        evidence={"note": "Driver phone rang out with no answer"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_TELEPHONY_FAILURE"
        assert final_state["requires_immediate_human_override"] is True
        assert final_state["call_status"] == "no_answer"
        assert "ops_alert_escalate" in final_state["tool_artifacts"]
        assert "routing_mutate_route" not in final_state["tool_artifacts"]
        assert "warehouse_reserve_dock" not in final_state["tool_artifacts"]


@pytest.mark.asyncio
async def test_simulation_3_malformed_webhook_rejection():
    """
    Simulation 3: Malformed telematics webhook is rejected before state/checkpoint creation.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad_payload = {
            "truck_id": "TRK-BAD",
        }
        response = await client.post("/webhook/telematics", json=bad_payload)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_simulation_4_hos_insufficient_reroute_blocked():
    """
    Simulation 4: HOS < 35 min attempt to reroute is blocked, routing tool NEVER called.
    """
    event_id = "sim_4_hos_block"
    initial_state = create_base_state(event_id)

    mock_triage_res = CallETriageStructuredResult(
        driver_verified_safe_location=True,
        reefer_engine_running=True,
        air_bulkhead_obstructed=False,
        cargo_sweating_detected=False,
        driver_reported_alarm_code="ALARM 18",
        driver_hos_minutes_remaining=20,  # Below 35 min threshold!
        selected_option="DIVERT_TO_COLD_HUB",
        emergency_reported=False,
    )
    mock_calle_out = CallETriageOutput(
        call_id=f"calle_{event_id}",
        status="completed",
        task_completed=True,
        completion_confidence=0.95,
        structured_result=mock_triage_res,
        evidence={"transcript_or_evidence_ref": "evd_hos_fail"},
    )

    with patch("src.agents.call_interrogation.call_e_initiate_triage", return_value=mock_calle_out):
        checkpointer = MemorySaver()
        graph = build_sentinel_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": event_id}}

        final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["disposition"] == "ESCALATED_HOS_BREACH"
        assert final_state["requires_immediate_human_override"] is True
        assert "routing_mutate_route" not in final_state["tool_artifacts"]
        assert "warehouse_reserve_dock" not in final_state["tool_artifacts"]
        assert "ops_alert_escalate" in final_state["tool_artifacts"]


def test_simulation_6_malformed_tool_output_pydantic_defense():
    """
    Simulation 6: Tool returns malformed data; Pydantic validation rejects it cleanly.
    """
    bad_data = {
        "driver_verified_safe_location": "not_a_bool",
        "reefer_engine_running": True,
    }
    with pytest.raises(ValidationError):
        StandaloneCallETriageStructuredResult.model_validate(bad_data)
