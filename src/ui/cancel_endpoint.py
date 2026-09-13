"""Pre-actuation cancellation handler for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 5 (Pattern: Pre-Actuation Cancel), Section 7
- DOCS/AGENT_MASTER_PLAN.md Section 8 (Emergency Stop Mechanism), Section 10 (Step 16)
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4, Section 11
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.ui.event_types import DataEscalationFiredEvent, StreamEndEvent
from src.ui.stream_handler import broadcaster

logger = logging.getLogger("cold_chain_sentinel.cancel")


class CancelRequestPayload(BaseModel):
    """Payload for pre-actuation session cancellation request."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["cancel"] = Field(default="cancel", description="Cancellation action descriptor")
    event_id: str = Field(..., description="Target excursion event identifier to cancel")


class CancelResponsePayload(BaseModel):
    """Response payload following cancellation evaluation."""

    model_config = ConfigDict(extra="ignore")

    accepted: bool = Field(..., description="Whether cancellation was accepted pre-actuation")
    reason: str = Field(..., description="Plain-language explanation of cancellation result")
    event_id: str = Field(..., description="Target excursion event identifier")
    timestamp: str = Field(..., description="ISO timestamp of cancellation evaluation")


async def handle_session_cancellation(
    payload: CancelRequestPayload,
    session_index: dict[str, dict[str, Any]],
    active_tasks: dict[str, Any],
    compiled_graph: Any = None,
) -> CancelResponsePayload:
    """Evaluate and execute session cancellation adhering to the pre-actuation policy.

    Rules:
    1. If actuation has not yet begun: accept cancellation, latch immediate human override to True,
       append 'manually cancelled' to escalation reasons, emit P0 alert, and route to escalation failure.
    2. If actuation has already committed a physical action: reject cancellation (no-naive-rollback),
       log the attempt, and leave committed fleet mutations intact.
    3. If session does not exist: raise 404 Not Found.
    """
    event_id = payload.event_id
    timestamp_str = datetime.now(timezone.utc).isoformat()

    if event_id not in session_index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Excursion session with event_id '{event_id}' not found",
        )

    session = session_index[event_id]
    final_state = session.get("final_state") or {}
    tool_artifacts = final_state.get("tool_artifacts") or {}

    # Check if mutating actuation has already executed
    actuation_tools = [
        "routing_mutate_route",
        "warehouse_reserve_dock",
        "maintenance_dispatch_ticket",
    ]
    has_actuated = any(tool in tool_artifacts for tool in actuation_tools)
    is_completed_autonomous = str(session.get("disposition", "")).startswith("AUTONOMOUSLY_")

    if has_actuated or is_completed_autonomous:
        logger.warning(
            f"Cancellation rejected for event_id: {event_id}. Actuation already committed."
        )
        return CancelResponsePayload(
            accepted=False,
            reason="Cancel received but actuation had already begun — see session log",
            event_id=event_id,
            timestamp=timestamp_str,
        )

    # Pre-actuation: Cancel accepted
    logger.info(f"Cancellation accepted for event_id: {event_id}. Locking human override latch.")

    # Cancel active background task if still running
    task = active_tasks.get(event_id)
    if task and not task.done():
        task.cancel()

    # Update in-memory session record
    session["status"] = "cancelled"
    session["disposition"] = "ESCALATED_MANUAL_OVERRIDE"
    session["override_required"] = True
    session["escalation_reasons"] = session.get("escalation_reasons", []) + ["manually cancelled"]

    # Emit real-time escalation and interruption stream events
    await broadcaster.publish(
        event_id,
        DataEscalationFiredEvent(
            escalation_reasons=["manually cancelled"],
            severity="P0",
            alert_id=f"alrt_{event_id}_cancel",
        ),
    )
    await broadcaster.publish(
        event_id,
        StreamEndEvent(reason="interrupted"),
    )

    return CancelResponsePayload(
        accepted=True,
        reason="Cancellation accepted pre-actuation. Session routed to escalation.",
        event_id=event_id,
        timestamp=timestamp_str,
    )
