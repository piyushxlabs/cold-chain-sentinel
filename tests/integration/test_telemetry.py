"""Integration tests for OpenTelemetry and Langfuse observability pipeline.

Authoritative specifications:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 6, Section 7a
- DOCS/AGENT_MASTER_PLAN.md Section 8, Section 10 (Step 18)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.telemetry.feedback_annotations import create_score
from src.telemetry.tracing import (
    clear_telemetry_registry,
    get_telemetry_registry,
    redact_sensitive_payload,
    trace_generation,
    trace_node,
    trace_tool,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure telemetry registry is clean before each test."""
    clear_telemetry_registry()
    yield
    clear_telemetry_registry()


def test_redact_sensitive_payload():
    """Verify sensitive credentials and tokens are redacted from telemetry payloads."""
    payload = {
        "event_id": "evt_123",
        "api_key": "AIzaSySecretKey",
        "nested": {
            "token": "bearer_jwt_token_here",
            "auth_header": "Bearer 12345",
            "truck_id": "TRK-902",
        },
        "public_field": "Lincoln Cold Storage",
    }

    redacted = redact_sensitive_payload(payload)
    assert redacted["event_id"] == "evt_123"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["auth_header"] == "[REDACTED]"
    assert redacted["nested"]["truck_id"] == "TRK-902"
    assert redacted["public_field"] == "Lincoln Cold Storage"


def test_trace_node_and_span_creation():
    """Verify node execution creates an OTel span and telemetry registry entry."""
    event_id = "evt_tel_001"

    with trace_node("enrichment", event_id=event_id, session_id="sess_tel_001") as node_record:
        assert node_record["node_name"] == "enrichment"
        assert node_record["status"] == "in-progress"

    registry = get_telemetry_registry()
    assert event_id in registry
    assert len(registry[event_id]["nodes"]) == 1

    stored_node = registry[event_id]["nodes"][0]
    assert stored_node["node_name"] == "enrichment"
    assert stored_node["status"] == "completed"
    assert "duration_ms" in stored_node


def test_trace_tool_invocation():
    """Verify tool execution records a span with redacted input/output digests."""
    event_id = "evt_tel_002"

    tool_record = trace_tool(
        tool_name="tms_lookup_driver_and_load",
        event_id=event_id,
        input_data={"truck_id": "TRK-8812", "api_key": "secret_key"},
        output_data={"tms_verified": True, "token": "session_token"},
        success=True,
        latency_ms=45.2,
    )

    assert tool_record["tool_name"] == "tms_lookup_driver_and_load"
    assert tool_record["success"] is True
    assert tool_record["input_digest"]["truck_id"] == "TRK-8812"
    assert tool_record["input_digest"]["api_key"] == "[REDACTED]"
    assert tool_record["output_digest"]["tms_verified"] is True
    assert tool_record["output_digest"]["token"] == "[REDACTED]"

    registry = get_telemetry_registry()
    assert len(registry[event_id]["tools"]) == 1


def test_trace_generation_provider_google():
    """Verify GenAI model generation span enforces provider: 'google' and GenAI semantics."""
    event_id = "evt_tel_003"
    model_name = "gemini-3.5-flash"

    gen_record = trace_generation(
        model_name=model_name,
        event_id=event_id,
        prompt="<evaluation_input>...</evaluation_input>",
        output={"claim_risk_level": "MODERATE", "review_confidence": 0.92},
        usage={"input_tokens": 450, "output_tokens": 120},
        latency_ms=180.5,
        provider="google",
    )

    assert gen_record["provider"] == "google"
    assert gen_record["model"] == model_name
    assert gen_record["event_id"] == event_id
    assert gen_record["usage"]["input_tokens"] == 450

    registry = get_telemetry_registry()
    assert len(registry[event_id]["generations"]) == 1
    assert registry[event_id]["generations"][0]["provider"] == "google"


def test_create_score_feedback_annotations():
    """Verify user feedback actions map to structured Langfuse scores (user_thumbs, user_rating)."""
    event_id = "evt_tel_004"

    # 1. Binary thumbs feedback
    score_thumbs = create_score(
        event_id=event_id,
        name="user_thumbs",
        value=True,
        comment="Accurate risk classification",
    )
    assert score_thumbs["score_name"] == "user_thumbs"
    assert score_thumbs["data_type"] == "BOOLEAN"
    assert score_thumbs["value"] is True
    assert score_thumbs["comment"] == "Accurate risk classification"

    # 2. Star rating feedback (1-5)
    score_stars = create_score(
        event_id=event_id,
        name="user_rating",
        value=5,
        comment="Perfect citation grounding",
    )
    assert score_stars["score_name"] == "user_rating"
    assert score_stars["data_type"] == "NUMERIC"
    assert score_stars["value"] == 5.0

    # 3. Overall outcome feedback
    score_outcome = create_score(
        event_id=event_id,
        name="overall_outcome",
        value=1.0,
    )
    assert score_outcome["score_name"] == "overall_outcome"
    assert score_outcome["data_type"] == "NUMERIC"

    registry = get_telemetry_registry()
    assert len(registry[event_id]["scores"]) == 3


@pytest.mark.asyncio
async def test_feedback_api_endpoints():
    """Verify FastAPI POST /sessions/{event_id}/feedback records telemetry scores."""
    event_id = "evt_tel_api_001"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit thumbs score
        res1 = await client.post(
            f"/sessions/{event_id}/feedback",
            json={"score_name": "user_thumbs", "value": True, "comment": "Fast and grounded"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "recorded"
        assert data1["score"]["score_name"] == "user_thumbs"
        assert data1["score"]["value"] is True

        # Submit numeric star rating
        res2 = await client.post(
            f"/api/sessions/{event_id}/feedback",
            json={"score_name": "user_rating", "value": 4, "comment": "Good response"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "recorded"
        assert data2["score"]["score_name"] == "user_rating"
        assert data2["score"]["value"] == 4.0

    registry = get_telemetry_registry()
    assert len(registry[event_id]["scores"]) == 2
