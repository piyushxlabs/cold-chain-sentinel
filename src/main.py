"""FastAPI backend server for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_MASTER_PLAN.md Section 7, Section 10 (Step 14)
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 2, Section 2a, Section 8
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4, Section 7, Section 10
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from src.agents.graph import build_sentinel_graph
from src.state.checkpointing import get_async_checkpointer, get_checkpoint_backend
from src.state.schema import (
    CargoManifest,
    Coordinates,
    RuntimeConfig,
    SentinelState,
)
from src.utils.sanitization import validate_e164_phone

logger = logging.getLogger("cold_chain_sentinel.api")
logging.basicConfig(level=logging.INFO)


class TelematicsWebhookPayload(BaseModel):
    """Incoming telematics reefer temperature excursion webhook payload."""

    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(..., description="Unique telematics excursion event identifier")
    session_id: str | None = Field(default=None, description="Optional session identifier")
    timestamp: str | None = Field(default=None, description="ISO timestamp of telematics excursion")
    truck_id: str = Field(..., description="Tractor/truck unit identifier")
    trailer_id: str = Field(..., description="Reefer trailer unit identifier")
    current_temp_f: float = Field(..., description="Current internal temperature reading in Fahrenheit")
    setpoint_temp_f: float = Field(..., description="Target setpoint temperature in Fahrenheit")
    temp_differential_f: float | None = Field(default=None, description="Calculated temperature differential")
    duration_minutes: int | None = Field(default=None, description="Duration of excursion in minutes")
    telematics_alarm_code: str | None = Field(default=None, description="Active telematics alarm code")
    current_coordinates: Coordinates | None = Field(default=None, description="Current GPS coordinates of the unit")
    target_destination: str | None = Field(default=None, description="Scheduled destination name/location")
    origin: str | None = Field(default=None, description="Origin shipping point")
    cargo_manifest: CargoManifest = Field(..., description="Bill of Lading and cargo parameters")
    driver_phone_e164: str = Field(..., description="Driver phone number in strict E.164 format")
    driver_name: str | None = Field(default=None, description="Driver legal name")
    driver_locale: str = Field(default="en-US", description="Driver preferred spoken locale")
    config: RuntimeConfig | None = Field(default=None, description="Optional execution runtime configuration")


class SessionSummary(BaseModel):
    """Summary record of an excursion triage session."""

    model_config = ConfigDict(extra="ignore")

    event_id: str
    session_id: str
    truck_id: str
    trailer_id: str
    driver_name: str
    commodity_type: str
    current_temp_f: float
    setpoint_temp_f: float
    status: str
    disposition: str | None = None
    override_required: bool = False
    timestamp: str


from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import MemorySaver

from src.ui.event_types import (
    GraphNodeTransitionEvent,
    StreamEndEvent,
    StreamErrorEvent,
)
from src.ui.stream_handler import (
    broadcaster,
    emit_node_execution_events,
    stream_sse_for_session,
)

# Global session metadata index for quick operations console querying
session_index: dict[str, dict[str, Any]] = {}
active_tasks: dict[str, asyncio.Task[Any]] = {}


async def execute_sentinel_workflow(
    compiled_graph: Any,
    initial_state: SentinelState,
    event_id: str,
) -> None:
    """Execute the compiled LangGraph StateGraph in the background with SSE broadcasting."""
    config = {"configurable": {"thread_id": event_id}}
    timestamp_str = datetime.now(timezone.utc).isoformat()
    try:
        logger.info(f"Starting LangGraph execution for event_id: {event_id}")
        session_index[event_id]["status"] = "in-progress"

        # Emit initial ingress entry event
        await broadcaster.publish(
            event_id,
            GraphNodeTransitionEvent(
                node="ingress",
                status="in-progress",
                timestamp=timestamp_str,
            ),
        )

        # Stream node updates granularly through LangGraph StateGraph
        async for update in compiled_graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            if isinstance(update, dict):
                for node_name, node_output in update.items():
                    if isinstance(node_output, dict):
                        await emit_node_execution_events(event_id, node_name, node_output)

        # Fetch final state snapshot from checkpointer
        state_snapshot = await compiled_graph.aget_state(config)
        final_state = state_snapshot.values if state_snapshot and state_snapshot.values else {}

        disposition = final_state.get("disposition")
        override = final_state.get("requires_immediate_human_override", False)
        logger.info(
            f"LangGraph execution finished for event_id: {event_id} with disposition: {disposition}"
        )

        if event_id in session_index:
            session_index[event_id]["status"] = "completed"
            session_index[event_id]["disposition"] = disposition
            session_index[event_id]["override_required"] = override
            session_index[event_id]["final_state"] = final_state

        # Emit terminal stream-end event
        await broadcaster.publish(
            event_id,
            StreamEndEvent(reason="success" if not override else "error"),
        )
    except Exception as exc:
        logger.error(f"Error executing LangGraph for event_id: {event_id}: {exc}", exc_info=True)
        if event_id in session_index:
            session_index[event_id]["status"] = "failed"
            session_index[event_id]["override_required"] = True

        await broadcaster.publish(
            event_id,
            StreamErrorEvent(code="WORKFLOW_ERROR", message=str(exc), recoverable=False),
        )
        await broadcaster.publish(event_id, StreamEndEvent(reason="error"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application checkpointer lifecycle and background resources."""
    logger.info("Initializing Cold Chain Sentinel FastAPI application...")
    backend = get_checkpoint_backend()
    logger.info(f"Using checkpoint backend: {backend}")

    # Use async checkpointer context manager
    async with get_async_checkpointer(backend) as checkpointer:
        compiled_graph = build_sentinel_graph(checkpointer=checkpointer)
        app.state.checkpointer = checkpointer
        app.state.compiled_graph = compiled_graph
        app.state.session_index = session_index
        app.state.active_tasks = active_tasks
        logger.info("LangGraph compiled with active checkpointer.")
        yield
        logger.info("Shutting down Cold Chain Sentinel server, cancelling in-flight background tasks...")
        for task in active_tasks.values():
            if not task.done():
                task.cancel()


app = FastAPI(
    title="Cold Chain Sentinel API",
    description="Autonomous Reefer Temperature Excursion & Telephony Compliance Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# Initialize app state defaults with MemorySaver fallback
app.state.session_index = session_index
app.state.active_tasks = active_tasks
app.state.compiled_graph = build_sentinel_graph(checkpointer=MemorySaver())

# Configure CORS for Next.js frontend cockpit
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Liveness and readiness health check endpoint."""
    return {
        "status": "healthy",
        "service": "cold-chain-sentinel",
        "version": "0.1.0",
        "checkpoint_backend": get_checkpoint_backend(),
        "primary_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        "fallback_model": os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro"),
        "client_mode": os.getenv("CLIENT_MODE", "mock"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post(
    "/webhook/telematics",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingress"],
)
@app.post(
    "/api/webhook/telematics",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingress"],
)
async def telematics_webhook(payload: TelematicsWebhookPayload) -> dict[str, Any]:
    """Ingest telematics temperature excursion alert and initiate triage graph."""
    if not validate_e164_phone(payload.driver_phone_e164):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid driver phone '{payload.driver_phone_e164}': Must follow strict E.164 format (e.g. +12065550198)",
        )

    session_id = payload.session_id or f"sess_{payload.event_id}"
    temp_diff = (
        payload.temp_differential_f
        if payload.temp_differential_f is not None
        else round(payload.current_temp_f - payload.setpoint_temp_f, 2)
    )

    # Construct initial typed SentinelState
    initial_state: SentinelState = {
        "event_id": payload.event_id,
        "session_id": session_id,
        "timestamp": payload.timestamp or datetime.now(timezone.utc).isoformat(),
        "truck_id": payload.truck_id,
        "trailer_id": payload.trailer_id,
        "current_temp_f": payload.current_temp_f,
        "setpoint_temp_f": payload.setpoint_temp_f,
        "temp_differential_f": temp_diff,
        "duration_minutes": payload.duration_minutes if payload.duration_minutes is not None else 15,
        "telematics_alarm_code": payload.telematics_alarm_code or "ALARM 18 - HIGH ENGINE TEMP",
        "current_coordinates": payload.current_coordinates or Coordinates(latitude=40.8136, longitude=-96.7026),
        "target_destination": payload.target_destination or "Omaha Distribution Center",
        "origin": payload.origin or "Kansas City Cold Hub",
        "cargo_manifest": payload.cargo_manifest,
        "driver_phone_e164": payload.driver_phone_e164,
        "driver_name": payload.driver_name or "Driver",
        "driver_locale": payload.driver_locale or "en-US",
        "config": payload.config
        or RuntimeConfig(
            trace_id=f"trc_{payload.event_id}",
            client_mode="mock" if os.getenv("CLIENT_MODE", "mock").lower() == "mock" else "live",
            max_tool_retry_attempts=3,
            min_hos_minutes_for_reroute=35,
        ),
        "requires_immediate_human_override": False,
        "escalation_reasons": [],
        "audit_trail": [],
        "error_logs": [],
        "tool_artifacts": {},
    }

    # Register in in-memory session index
    session_index[payload.event_id] = {
        "event_id": payload.event_id,
        "session_id": session_id,
        "truck_id": payload.truck_id,
        "trailer_id": payload.trailer_id,
        "driver_name": payload.driver_name or "Driver",
        "commodity_type": payload.cargo_manifest.commodity_type,
        "current_temp_f": payload.current_temp_f,
        "setpoint_temp_f": payload.setpoint_temp_f,
        "status": "pending",
        "disposition": None,
        "override_required": False,
        "timestamp": payload.timestamp or datetime.now(timezone.utc).isoformat(),
    }

    # Launch background LangGraph StateGraph execution
    compiled_graph = getattr(app.state, "compiled_graph", None)
    if compiled_graph is None:
        # Fallback for testing with transient checkpointer
        compiled_graph = build_sentinel_graph()

    task = asyncio.create_task(
        execute_sentinel_workflow(compiled_graph, initial_state, payload.event_id)
    )
    active_tasks[payload.event_id] = task

    return {
        "status": "accepted",
        "event_id": payload.event_id,
        "session_id": session_id,
        "message": "Telematics excursion event accepted for autonomous voice triage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/sessions", tags=["Sessions"])
@app.get("/api/sessions", tags=["Sessions"])
async def list_sessions() -> list[dict[str, Any]]:
    """List all tracked excursion triage sessions for the operations queue."""
    return list(session_index.values())


@app.get("/sessions/{event_id}/state", tags=["Sessions"])
@app.get("/api/sessions/{event_id}/state", tags=["Sessions"])
async def get_session_state(event_id: str) -> dict[str, Any]:
    """Retrieve full checkpointed SentinelState snapshot for a given event_id."""
    compiled_graph = getattr(app.state, "compiled_graph", None)
    config = {"configurable": {"thread_id": event_id}}

    if compiled_graph is not None:
        try:
            snapshot = await compiled_graph.aget_state(config)
            if snapshot and snapshot.values:
                # Convert any Pydantic submodels or custom objects to dicts if needed
                values = dict(snapshot.values)
                return {
                    "event_id": event_id,
                    "state": values,
                    "next_nodes": list(snapshot.next),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as exc:
            logger.warning(f"Error reading checkpoint snapshot for {event_id}: {exc}")

    if event_id in session_index:
        final_state = session_index[event_id].get("final_state")
        return {
            "event_id": event_id,
            "session_summary": session_index[event_id],
            "state": dict(final_state) if final_state else None,
            "message": "Session indexed" if final_state is None else "Session completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Excursion session with event_id '{event_id}' not found",
    )


@app.get("/sessions/{event_id}/stream", tags=["Streaming"])
@app.get("/api/sessions/{event_id}/stream", tags=["Streaming"])
async def stream_session_events(event_id: str):
    """Server-Sent Events (SSE) live data stream endpoint for the incident timeline."""
    return StreamingResponse(
        stream_sse_for_session(event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

