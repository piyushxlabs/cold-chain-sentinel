"""Integration tests for Cold Chain Sentinel FastAPI backend server.

Authoritative specifications:
- DOCS/AGENT_MASTER_PLAN.md Section 10 (Step 14)
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 2, Section 8
"""

import asyncio
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
def mock_webhook_payload() -> dict:
    """Fixture for Section 9.1 Simple Case excursion webhook."""
    return {
        "event_id": "evt_srv_test_001",
        "session_id": "sess_srv_test_001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "current_temp_f": 38.5,
        "setpoint_temp_f": 34.0,
        "temp_differential_f": 4.5,
        "duration_minutes": 25,
        "telematics_alarm_code": "ALARM 18 - HIGH ENGINE TEMP",
        "current_coordinates": {
            "latitude": 40.8136,
            "longitude": -96.7026,
        },
        "target_destination": "Omaha Distribution Center",
        "origin": "Kansas City Cold Hub",
        "cargo_manifest": {
            "bol_number": "BOL-78901",
            "commodity_type": "Dairy",
            "min_temp_f": 32.0,
            "max_temp_f": 36.0,
            "max_allowable_excursion_minutes": 60,
            "shipper_name": "Midwest Dairy Logistics",
        },
        "driver_phone_e164": "+12065550198",
        "driver_name": "Marcus Vance",
        "driver_locale": "en-US",
        "config": {
            "trace_id": "trc_srv_test_001",
            "client_mode": "mock",
            "max_tool_retry_attempts": 3,
            "min_hos_minutes_for_reroute": 35,
        },
    }


@pytest.mark.asyncio
async def test_health_check():
    """Verify /health and /api/health endpoints return 200 OK and valid metadata."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Test /health
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "cold-chain-sentinel"
        assert "checkpoint_backend" in data
        assert "primary_model" in data

        # 2. Test /api/health alias
        res_alias = await client.get("/api/health")
        assert res_alias.status_code == 200
        assert res_alias.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_telematics_webhook_valid_ingestion(mock_webhook_payload: dict):
    """Verify valid telematics webhook is accepted with 202 and completes triage graph."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Trigger webhook ingress
        response = await client.post("/webhook/telematics", json=mock_webhook_payload)
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_id"] == "evt_srv_test_001"
        assert data["session_id"] == "sess_srv_test_001"

        # Wait for background task to complete execution
        task = app.state.active_tasks.get("evt_srv_test_001")
        if task:
            await task

        # Check /sessions list
        sessions_res = await client.get("/sessions")
        assert sessions_res.status_code == 200
        sessions = sessions_res.json()
        matching = [s for s in sessions if s["event_id"] == "evt_srv_test_001"]
        assert len(matching) == 1
        assert matching[0]["status"] == "completed"
        assert matching[0]["disposition"] == "AUTONOMOUSLY_DIVERTED"
        assert matching[0]["override_required"] is False

        # Check /sessions/{event_id}/state
        state_res = await client.get("/sessions/evt_srv_test_001/state")
        assert state_res.status_code == 200
        state_data = state_res.json()
        assert state_data["event_id"] == "evt_srv_test_001"
        assert state_data["state"] is not None
        assert state_data["state"]["agreed_action"] == "DIVERT_TO_EMERGENCY_COLD_HUB"
        assert state_data["state"]["disposition"] == "AUTONOMOUSLY_DIVERTED"


@pytest.mark.asyncio
async def test_telematics_webhook_invalid_phone_rejected(mock_webhook_payload: dict):
    """Verify webhook with invalid non-E.164 phone is rejected with 422."""
    invalid_payload = dict(mock_webhook_payload)
    invalid_payload["event_id"] = "evt_srv_test_invalid_phone"
    invalid_payload["driver_phone_e164"] = "555-0198"  # Invalid format

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/webhook/telematics", json=invalid_payload)
        assert response.status_code == 422
        assert "E.164" in response.json()["detail"]


@pytest.mark.asyncio
async def test_session_state_not_found():
    """Verify non-existent event_id returns 404 Not Found."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/sessions/evt_non_existent_9999/state")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
