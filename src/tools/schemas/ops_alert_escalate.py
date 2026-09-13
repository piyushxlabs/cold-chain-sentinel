"""Tool Schema: ops_alert_escalate.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class OpsAlertInput(BaseModel):
    """Input payload for human fleet operations P0 alert."""

    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(..., description="Excursion event identifier")
    escalation_reasons: list[str] = Field(..., description="Every rule/condition that triggered human escalation")
    severity_level: Literal["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM"] = Field(
        default="P0_CRITICAL", description="Operational alert priority level"
    )
    state_summary: dict[str, Any] = Field(..., description="Snapshot of telematics, driver, and cargo evidence")


class OpsAlertOutput(BaseModel):
    """Result of operations alert dispatch."""

    model_config = ConfigDict(extra="ignore")

    alert_id: str = Field(..., description="Assigned alert identifier in incident management system")
    delivered: bool = Field(..., description="Whether alert successfully reached fleet operations paging channels")
    channel: str = Field(default="OPS_PAGER_P0", description="Dispatch channel utilized")
    error: Optional[str] = Field(default=None, description="Error message if alert delivery encountered failure")
