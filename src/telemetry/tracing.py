"""OpenTelemetry and Langfuse observability instrumentation.

Authoritative specifications:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 6, Section 7a
- DOCS/AGENT_MASTER_PLAN.md Section 8, Section 10 (Step 18)
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Generator

logger = logging.getLogger("cold_chain_sentinel.tracing")

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# In-memory registry for session traces, spans, and scores (enables offline inspection & testing)
_TELEMETRY_REGISTRY: dict[str, dict[str, Any]] = {}


def get_telemetry_registry() -> dict[str, dict[str, Any]]:
    """Return the global in-memory telemetry registry for inspection and testing."""
    return _TELEMETRY_REGISTRY


def clear_telemetry_registry() -> None:
    """Clear in-memory telemetry registry."""
    _TELEMETRY_REGISTRY.clear()


def get_langfuse_client() -> Any | None:
    """Initialize Langfuse client if credentials are configured in environment.

    Returns None if credentials are not provided, enabling graceful offline fallback.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    if not public_key or not secret_key or "Your" in public_key:
        return None

    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
    except Exception:
        return None


def get_otel_tracer(name: str = "cold-chain-sentinel") -> trace.Tracer:
    """Get or initialize the OpenTelemetry Tracer."""
    return trace.get_tracer(name)


def redact_sensitive_payload(data: Any) -> Any:
    """Redact sensitive keys (API keys, tokens, auth headers) from telemetry payloads."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(secret_kw in k.lower() for secret_kw in ["key", "token", "auth", "secret", "password"]):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_sensitive_payload(v)
            else:
                redacted[k] = v
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_payload(item) for item in data]
    return data


def ensure_session_trace(event_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Ensure a session trace entry exists in the local telemetry registry."""
    if event_id not in _TELEMETRY_REGISTRY:
        _TELEMETRY_REGISTRY[event_id] = {
            "event_id": event_id,
            "session_id": session_id or f"sess_{event_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nodes": [],
            "tools": [],
            "generations": [],
            "scores": [],
        }
    return _TELEMETRY_REGISTRY[event_id]


@contextmanager
def trace_node(
    node_name: str,
    event_id: str,
    session_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager for tracing a LangGraph node execution.

    Emits OpenTelemetry span and records node entry/exit in local telemetry registry.
    """
    tracer = get_otel_tracer()
    session_data = ensure_session_trace(event_id, session_id)
    start_time = time.time()

    node_record: dict[str, Any] = {
        "node_name": node_name,
        "event_id": event_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "in-progress",
    }

    with tracer.start_as_current_span(f"node:{node_name}") as span:
        span.set_attribute("node.name", node_name)
        span.set_attribute("event_id", event_id)
        if session_id:
            span.set_attribute("session_id", session_id)

        try:
            yield node_record
            node_record["status"] = "completed"
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            node_record["status"] = "error"
            node_record["error"] = str(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise
        finally:
            node_record["duration_ms"] = round((time.time() - start_time) * 1000, 2)
            node_record["end_time"] = datetime.now(timezone.utc).isoformat()
            session_data["nodes"].append(node_record)


def trace_tool(
    tool_name: str,
    event_id: str,
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    success: bool = True,
    latency_ms: float = 0.0,
    error: str | None = None,
) -> dict[str, Any]:
    """Record an OpenTelemetry span and telemetry entry for a tool client invocation.

    Applies strict input/output digest redaction.
    """
    tracer = get_otel_tracer()
    session_data = ensure_session_trace(event_id)

    redacted_input = redact_sensitive_payload(input_data or {})
    redacted_output = redact_sensitive_payload(output_data or {})

    tool_record: dict[str, Any] = {
        "tool_name": tool_name,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "latency_ms": latency_ms,
        "input_digest": redacted_input,
        "output_digest": redacted_output,
        "error": error,
    }

    with tracer.start_as_current_span(f"tool:{tool_name}") as span:
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("event_id", event_id)
        span.set_attribute("tool.success", success)
        span.set_attribute("tool.latency_ms", latency_ms)

        if success:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, description=error or "Tool execution failed"))

    session_data["tools"].append(tool_record)
    return tool_record


def trace_generation(
    model_name: str,
    event_id: str,
    prompt: Any,
    output: Any,
    usage: dict[str, Any] | None = None,
    latency_ms: float = 0.0,
    provider: str = "google",
    span_name: str = "compliance_review_generation",
) -> dict[str, Any]:
    """Record a Langfuse Generation span and OpenTelemetry GenAI Semantic Conventions span.

    Enforces:
    - Provider: strictly "google"
    - Model: dynamic Gemini model string
    - Semantic convention attributes: gen_ai.system, gen_ai.request.model, gen_ai.response.model
    """
    tracer = get_otel_tracer()
    session_data = ensure_session_trace(event_id)

    gen_record: dict[str, Any] = {
        "span_name": span_name,
        "provider": provider,
        "model": model_name,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": redact_sensitive_payload(prompt),
        "output": redact_sensitive_payload(output),
        "usage": usage or {},
        "latency_ms": latency_ms,
    }

    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("gen_ai.system", provider)
        span.set_attribute("gen_ai.request.model", model_name)
        span.set_attribute("gen_ai.response.model", model_name)
        span.set_attribute("gen_ai.event_id", event_id)

        if usage:
            if "input_tokens" in usage:
                span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
            if "output_tokens" in usage:
                span.set_attribute("gen_ai.usage.output_tokens", usage["output_tokens"])

        span.set_status(Status(StatusCode.OK))

    # Export to Langfuse if client is available
    langfuse_client = get_langfuse_client()
    if langfuse_client:
        try:
            # Langfuse generation creation
            langfuse_client.create_event(
                name=span_name,
                metadata={
                    "provider": provider,
                    "model": model_name,
                    "event_id": event_id,
                    "latency_ms": latency_ms,
                    "usage": usage,
                },
                input=gen_record["prompt"],
                output=gen_record["output"],
            )
        except Exception as exc:
            logger.warning(f"Langfuse generation event export failed: {exc}")

    session_data["generations"].append(gen_record)
    return gen_record
