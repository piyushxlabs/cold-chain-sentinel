"""Server-Sent Events (SSE) streaming handler and pub/sub broadcaster.

Authoritative specification:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 2, Section 2a, Section 4a
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from src.ui.event_types import (
    BaseStreamEvent,
    DataEscalationFiredEvent,
    DataStateUpdateEvent,
    DataStructuredOutputEvent,
    GraphNodeTransitionEvent,
    StreamEndEvent,
    StreamErrorEvent,
    StreamEvent,
    ToolInputAvailableEvent,
    ToolInputStartEvent,
    ToolOutputAvailableEvent,
)

logger = logging.getLogger("cold_chain_sentinel.streaming")


class SessionEventBroadcaster:
    """Manages real-time SSE event publishing and multi-client fanout per event_id."""

    def __init__(self) -> None:
        self._buffers: dict[str, list[StreamEvent]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[StreamEvent]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event_id: str, event: StreamEvent) -> None:
        """Publish an event to all active subscriber queues and persist in buffer."""
        async with self._lock:
            if event_id not in self._buffers:
                self._buffers[event_id] = []
            self._buffers[event_id].append(event)

            subscribers = self._subscribers.get(event_id, set()).copy()

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Subscriber queue full for event_id: {event_id}")

    async def subscribe(
        self, event_id: str, timeout_seconds: float = 30.0
    ) -> AsyncGenerator[StreamEvent, None]:
        """Subscribe to a session stream, replaying buffered history first."""
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=200)

        async with self._lock:
            if event_id not in self._subscribers:
                self._subscribers[event_id] = set()
            self._subscribers[event_id].add(queue)
            history = self._buffers.get(event_id, []).copy()

        # Replay history first
        for event in history:
            yield event
            if event.type == "stream-end":
                return

        # Listen for live events
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
                    yield event
                    if event.type == "stream-end":
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat ping
                    yield None
        finally:
            async with self._lock:
                if event_id in self._subscribers:
                    self._subscribers[event_id].discard(queue)
                    if not self._subscribers[event_id]:
                        del self._subscribers[event_id]

    def get_buffered_events(self, event_id: str) -> list[StreamEvent]:
        """Retrieve all buffered events for a session."""
        return self._buffers.get(event_id, []).copy()

    def clear_session(self, event_id: str) -> None:
        """Clear event buffers and subscribers for a session."""
        self._buffers.pop(event_id, None)
        self._subscribers.pop(event_id, None)


# Global event broadcaster instance
broadcaster = SessionEventBroadcaster()


def format_sse(event: StreamEvent | None) -> str:
    """Format a StreamEvent into a standard Server-Sent Event frame.

    Vercel AI SDK Data Stream Protocol format:
    data: {"type": "...", ...}\n\n
    """
    if event is None:
        # Keep-alive heartbeat comment frame
        return ": ping\n\n"

    # Export with aliases (e.g., 'schema' instead of 'schema_name')
    payload = event.model_dump(by_alias=True)
    json_str = json.dumps(payload, default=str)
    return f"data: {json_str}\n\n"


async def stream_sse_for_session(event_id: str) -> AsyncGenerator[str, None]:
    """Async generator streaming SSE frames for a given session event_id."""
    async for event in broadcaster.subscribe(event_id):
        yield format_sse(event)


def map_field_to_reducer(field: str) -> str:
    """Resolve declared state reducer for a SentinelState field."""
    if field == "requires_immediate_human_override":
        return "monotonic-or"
    if field in ["audit_trail", "error_logs", "escalation_reasons"]:
        return "append-only"
    if field in ["tool_artifacts"]:
        return "merge-by-key"
    if field in [
        "event_id",
        "session_id",
        "truck_id",
        "trailer_id",
        "cargo_manifest",
        "driver_phone_e164",
        "config",
    ]:
        return "immutable-after-init"
    return "last-write-wins"


async def emit_node_execution_events(
    event_id: str,
    node_name: str,
    node_output: dict[str, Any],
) -> None:
    """Emit granular typed events for a completed LangGraph node."""
    timestamp_str = datetime.now(timezone.utc).isoformat()

    # 1. Emit structured output if produced
    if "compliance_review" in node_output and node_output["compliance_review"]:
        review = node_output["compliance_review"]
        review_dict = review.model_dump() if hasattr(review, "model_dump") else dict(review)
        await broadcaster.publish(
            event_id,
            DataStructuredOutputEvent(
                node="compliance_review",
                schema="ComplianceReviewDecision",
                value=review_dict,
            ),
        )

    # 2. Emit tool execution events if tool artifacts were created
    if "tool_artifacts" in node_output and node_output["tool_artifacts"]:
        for tool_name, artifact in node_output["tool_artifacts"].items():
            call_id = getattr(artifact, "tool_call_id", f"call_{tool_name}")
            t_name = getattr(artifact, "tool_name", tool_name)
            t_status = getattr(artifact, "status", "SUCCESS")
            payload = getattr(artifact, "payload", {})

            await broadcaster.publish(
                event_id,
                ToolInputStartEvent(toolCallId=call_id, toolName=t_name),
            )
            await broadcaster.publish(
                event_id,
                ToolInputAvailableEvent(toolCallId=call_id, toolName=t_name, input={}),
            )
            await broadcaster.publish(
                event_id,
                ToolOutputAvailableEvent(
                    toolCallId=call_id,
                    toolName=t_name,
                    output=payload if isinstance(payload, dict) else {},
                    success=(t_status == "SUCCESS"),
                ),
            )

    # 3. Emit escalation alert if triggered
    disposition = str(node_output.get("disposition", ""))
    override = node_output.get("requires_immediate_human_override", False)
    reasons = node_output.get("escalation_reasons", [])
    if "ESCALATED" in disposition or (override and reasons):
        await broadcaster.publish(
            event_id,
            DataEscalationFiredEvent(
                escalation_reasons=reasons if reasons else ["Manual human override required"],
                severity="P0",
                alert_id=f"alrt_{event_id}",
            ),
        )

    # 4. Emit data state updates for each updated state field
    for field, val in node_output.items():
        if field in ["audit_trail", "error_logs", "tool_artifacts"]:
            continue
        reducer = map_field_to_reducer(field)
        serializable_val = val.model_dump() if hasattr(val, "model_dump") else val
        await broadcaster.publish(
            event_id,
            DataStateUpdateEvent(field=field, reducer=reducer, value=serializable_val),
        )

    # 5. Emit node complete transition
    await broadcaster.publish(
        event_id,
        GraphNodeTransitionEvent(
            node=node_name,
            status="complete",
            timestamp=timestamp_str,
        ),
    )
