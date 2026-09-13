"""Typed streaming event data contract definitions for Cold Chain Sentinel.

Authoritative specification:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 2a, Section 4a
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class BaseStreamEvent(BaseModel):
    """Base class for all Server-Sent Events emitted to the frontend cockpit."""

    model_config = ConfigDict(extra="ignore")


class GraphNodeTransitionEvent(BaseStreamEvent):
    """Event emitted on LangGraph StateGraph node entry or completion."""

    type: Literal["graph-node-transition"] = "graph-node-transition"
    node: str = Field(..., description="Name of the LangGraph node")
    status: Literal["pending", "in-progress", "complete", "failed", "skipped"] = Field(
        ..., description="Current status of the node"
    )
    timestamp: str = Field(..., description="ISO timestamp of transition")


class ToolInputStartEvent(BaseStreamEvent):
    """Event emitted immediately before tool execution begins."""

    type: Literal["tool-input-start"] = "tool-input-start"
    toolCallId: str = Field(..., description="Unique tool call execution identifier")
    toolName: str = Field(..., description="Name of the fleet capability or telephony tool")


class ToolInputAvailableEvent(BaseStreamEvent):
    """Event emitted when tool parameters are constructed."""

    type: Literal["tool-input-available"] = "tool-input-available"
    toolCallId: str = Field(..., description="Unique tool call execution identifier")
    toolName: str = Field(..., description="Name of the tool")
    input: dict[str, Any] = Field(..., description="Sanitized tool input parameters")


class ToolOutputAvailableEvent(BaseStreamEvent):
    """Event emitted on tool execution completion with output."""

    type: Literal["tool-output-available"] = "tool-output-available"
    toolCallId: str = Field(..., description="Unique tool call execution identifier")
    toolName: str = Field(..., description="Name of the tool")
    output: dict[str, Any] = Field(..., description="Pydantic tool output payload")
    success: bool = Field(..., description="Whether tool execution succeeded")


class DataStructuredOutputEvent(BaseStreamEvent):
    """Event emitted when Google Gemini produces ComplianceReviewDecision."""

    type: Literal["data-structured-output"] = "data-structured-output"
    node: str = Field(default="compliance_review", description="Originating node")
    schema_name: str = Field(
        default="ComplianceReviewDecision",
        alias="schema",
        description="Structured output schema name",
    )
    value: dict[str, Any] = Field(..., description="Full structured decision object")


class DataStateUpdateEvent(BaseStreamEvent):
    """Event emitted when a SentinelState field is written."""

    type: Literal["data-state-update"] = "data-state-update"
    field: str = Field(..., description="SentinelState field name")
    reducer: Literal[
        "append-only", "merge-by-key", "last-write-wins", "immutable-after-init", "monotonic-or"
    ] = Field(..., description="Declared state reducer")
    value: Any = Field(..., description="Written field value")


class DataEscalationFiredEvent(BaseStreamEvent):
    """Event emitted when operations P0/P1 alert is fired."""

    type: Literal["data-escalation-fired"] = "data-escalation-fired"
    escalation_reasons: list[str] = Field(..., description="List of reasons triggering human escalation")
    severity: Literal["P0", "P1"] = Field(..., description="Incident severity level")
    alert_id: str = Field(..., description="Generated alert identifier")


class StreamErrorEvent(BaseStreamEvent):
    """Event emitted on unrecoverable or transient error."""

    type: Literal["error"] = "error"
    code: str = Field(..., description="Error classification code")
    message: str = Field(..., description="Human-readable error explanation")
    recoverable: bool = Field(default=False, description="Whether error is being retried")


class StreamEndEvent(BaseStreamEvent):
    """Terminal event freezing the timeline."""

    type: Literal["stream-end"] = "stream-end"
    reason: Literal["success", "interrupted", "error"] = Field(
        ..., description="Reason for stream termination"
    )


# Union type for all streaming events
StreamEvent = (
    GraphNodeTransitionEvent
    | ToolInputStartEvent
    | ToolInputAvailableEvent
    | ToolOutputAvailableEvent
    | DataStructuredOutputEvent
    | DataStateUpdateEvent
    | DataEscalationFiredEvent
    | StreamErrorEvent
    | StreamEndEvent
)
