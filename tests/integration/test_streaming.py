"""Integration test suite for typed SSE streaming layer and event contract.

Authoritative specification:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 2a, Section 4a
- DOCS/AGENT_MASTER_PLAN.md Section 10 (Step 15)
"""

import asyncio
import json
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.ui.event_types import (
    DataEscalationFiredEvent,
    DataStateUpdateEvent,
    DataStructuredOutputEvent,
    GraphNodeTransitionEvent,
    StreamEndEvent,
    StreamErrorEvent,
    ToolInputAvailableEvent,
    ToolInputStartEvent,
    ToolOutputAvailableEvent,
)
from src.ui.stream_handler import broadcaster, format_sse


def test_typed_event_models_serialization():
    """Verify all 9 SSE event models serialize to JSON matching the Section 2a data contract."""
    # 1. GraphNodeTransitionEvent
    e1 = GraphNodeTransitionEvent(
        node="enrichment", status="in-progress", timestamp="2026-09-13T00:00:00Z"
    )
    d1 = json.loads(e1.model_dump_json(by_alias=True))
    assert d1["type"] == "graph-node-transition"
    assert d1["node"] == "enrichment"
    assert d1["status"] == "in-progress"

    # 2. ToolInputStartEvent
    e2 = ToolInputStartEvent(toolCallId="call_001", toolName="tms_lookup_driver_and_load")
    d2 = json.loads(e2.model_dump_json(by_alias=True))
    assert d2["type"] == "tool-input-start"
    assert d2["toolCallId"] == "call_001"

    # 3. ToolInputAvailableEvent
    e3 = ToolInputAvailableEvent(
        toolCallId="call_001", toolName="tms_lookup", input={"truck_id": "TRK-1"}
    )
    d3 = json.loads(e3.model_dump_json(by_alias=True))
    assert d3["type"] == "tool-input-available"
    assert d3["input"]["truck_id"] == "TRK-1"

    # 4. ToolOutputAvailableEvent
    e4 = ToolOutputAvailableEvent(
        toolCallId="call_001", toolName="tms_lookup", output={"tms_verified": True}, success=True
    )
    d4 = json.loads(e4.model_dump_json(by_alias=True))
    assert d4["type"] == "tool-output-available"
    assert d4["success"] is True

    # 5. DataStructuredOutputEvent
    e5 = DataStructuredOutputEvent(
        node="compliance_review",
        schema="ComplianceReviewDecision",
        value={"claim_risk_level": "LOW", "review_confidence": 0.95},
    )
    d5 = json.loads(e5.model_dump_json(by_alias=True))
    assert d5["type"] == "data-structured-output"
    assert d5["schema"] == "ComplianceReviewDecision"
    assert d5["value"]["claim_risk_level"] == "LOW"

    # 6. DataStateUpdateEvent
    e6 = DataStateUpdateEvent(
        field="requires_immediate_human_override",
        reducer="monotonic-or",
        value=True,
    )
    d6 = json.loads(e6.model_dump_json(by_alias=True))
    assert d6["type"] == "data-state-update"
    assert d6["reducer"] == "monotonic-or"

    # 7. DataEscalationFiredEvent
    e7 = DataEscalationFiredEvent(
        escalation_reasons=["HOS breach"], severity="P0", alert_id="alrt_001"
    )
    d7 = json.loads(e7.model_dump_json(by_alias=True))
    assert d7["type"] == "data-escalation-fired"
    assert d7["severity"] == "P0"

    # 8. StreamErrorEvent
    e8 = StreamErrorEvent(code="CALLE_NO_ANSWER", message="Driver unreachable", recoverable=False)
    d8 = json.loads(e8.model_dump_json(by_alias=True))
    assert d8["type"] == "error"
    assert d8["code"] == "CALLE_NO_ANSWER"

    # 9. StreamEndEvent
    e9 = StreamEndEvent(reason="success")
    d9 = json.loads(e9.model_dump_json(by_alias=True))
    assert d9["type"] == "stream-end"
    assert d9["reason"] == "success"


@pytest.mark.asyncio
async def test_session_event_broadcaster_pub_sub():
    """Verify SessionEventBroadcaster fans out events to subscribers and replays buffer."""
    event_id = "evt_stream_test_001"
    broadcaster.clear_session(event_id)

    # 1. Publish before subscriber connects (buffered)
    e1 = GraphNodeTransitionEvent(
        node="ingress", status="complete", timestamp=datetime.now(timezone.utc).isoformat()
    )
    await broadcaster.publish(event_id, e1)

    received_events = []

    async def consumer():
        async for ev in broadcaster.subscribe(event_id, timeout_seconds=1.0):
            if ev is not None:
                received_events.append(ev)
                if ev.type == "stream-end":
                    break

    task = asyncio.create_task(consumer())

    # Allow subscriber to attach
    await asyncio.sleep(0.05)

    # 2. Publish live event
    e2 = StreamEndEvent(reason="success")
    await broadcaster.publish(event_id, e2)

    await asyncio.wait_for(task, timeout=2.0)

    assert len(received_events) == 2
    assert received_events[0].type == "graph-node-transition"
    assert received_events[1].type == "stream-end"


@pytest.mark.asyncio
async def test_end_to_end_sse_stream_endpoint():
    """Verify /sessions/{event_id}/stream returns SSE frames for a triage execution."""
    event_id = "evt_stream_e2e_001"
    payload = {
        "event_id": event_id,
        "session_id": f"sess_{event_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "current_temp_f": 38.5,
        "setpoint_temp_f": 34.0,
        "temp_differential_f": 4.5,
        "duration_minutes": 25,
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
        "config": {
            "trace_id": f"trc_{event_id}",
            "client_mode": "mock",
            "max_tool_retry_attempts": 3,
            "min_hos_minutes_for_reroute": 35,
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Trigger webhook ingress
        post_res = await client.post("/webhook/telematics", json=payload)
        assert post_res.status_code == 202

        # Await background execution
        task = app.state.active_tasks.get(event_id)
        if task:
            await task

        # Connect to SSE stream endpoint
        stream_res = await client.get(f"/sessions/{event_id}/stream")
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers.get("content-type", "")

        # Read and parse SSE body
        body = stream_res.text
        lines = [line for line in body.split("\n") if line.startswith("data: ")]
        assert len(lines) > 0

        parsed_events = [json.loads(line[6:]) for line in lines]
        event_types = [ev["type"] for ev in parsed_events]

        # Verify key event types exist in stream
        assert "graph-node-transition" in event_types
        assert "data-state-update" in event_types
        assert "stream-end" in event_types
        assert parsed_events[-1]["type"] == "stream-end"
        assert parsed_events[-1]["reason"] == "success"
