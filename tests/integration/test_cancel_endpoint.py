"""Integration test suite for pre-actuation cancellation endpoint.

Authoritative specification:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 5 (Pattern: Pre-Actuation Cancel), Section 7
- DOCS/AGENT_MASTER_PLAN.md Section 8, Section 10 (Step 16)
"""

import asyncio
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, session_index
from src.state.schema import ToolCallResult
from src.ui.stream_handler import broadcaster


@pytest.mark.asyncio
async def test_cancel_pre_actuation_accepted():
    """Verify cancellation before actuation is accepted and latches human override."""
    event_id = "evt_cancel_pre_actuation_001"
    session_index[event_id] = {
        "event_id": event_id,
        "session_id": f"sess_{event_id}",
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "driver_name": "Marcus Vance",
        "commodity_type": "Dairy",
        "current_temp_f": 38.5,
        "setpoint_temp_f": 34.0,
        "status": "in-progress",
        "disposition": None,
        "override_required": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final_state": {},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/sessions/{event_id}/cancel",
            json={"action": "cancel", "event_id": event_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["event_id"] == event_id
        assert "pre-actuation" in data["reason"].lower()

        # Verify session state was locked to override
        assert session_index[event_id]["status"] == "cancelled"
        assert session_index[event_id]["override_required"] is True
        assert session_index[event_id]["disposition"] == "ESCALATED_MANUAL_OVERRIDE"
        assert "manually cancelled" in session_index[event_id]["escalation_reasons"]

        # Verify stream events emitted
        buffered = broadcaster.get_buffered_events(event_id)
        event_types = [ev.type for ev in buffered]
        assert "data-escalation-fired" in event_types
        assert "stream-end" in event_types
        stream_end_ev = [ev for ev in buffered if ev.type == "stream-end"][0]
        assert stream_end_ev.reason == "interrupted"


@pytest.mark.asyncio
async def test_cancel_post_actuation_rejected():
    """Verify cancellation after actuation is rejected without naive rollback."""
    event_id = "evt_cancel_post_actuation_001"
    session_index[event_id] = {
        "event_id": event_id,
        "session_id": f"sess_{event_id}",
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "driver_name": "Marcus Vance",
        "commodity_type": "Dairy",
        "current_temp_f": 38.5,
        "setpoint_temp_f": 34.0,
        "status": "completed",
        "disposition": "AUTONOMOUSLY_DIVERTED",
        "override_required": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final_state": {
            "disposition": "AUTONOMOUSLY_DIVERTED",
            "tool_artifacts": {
                "routing_mutate_route": ToolCallResult(
                    tool_call_id="call_route_001",
                    tool_name="routing_mutate_route",
                    status="SUCCESS",
                    payload={"route_mutation_confirmed": True},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    latency_ms=120.0,
                ),
                "warehouse_reserve_dock": ToolCallResult(
                    tool_call_id="call_wh_001",
                    tool_name="warehouse_reserve_dock",
                    status="SUCCESS",
                    payload={"reservation_confirmed": True},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    latency_ms=90.0,
                ),
            },
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/sessions/{event_id}/cancel",
            json={"action": "cancel", "event_id": event_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is False
        assert data["event_id"] == event_id
        assert "already begun" in data["reason"].lower()

        # Verify disposition was preserved without rollback
        assert session_index[event_id]["disposition"] == "AUTONOMOUSLY_DIVERTED"
        assert session_index[event_id]["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_non_existent_session_404():
    """Verify cancelling non-existent session returns 404 Not Found."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/sessions/evt_cancel_ghost_9999/cancel",
            json={"action": "cancel", "event_id": "evt_cancel_ghost_9999"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
