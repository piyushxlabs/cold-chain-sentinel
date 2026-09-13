"""Tool Schema: maintenance_dispatch_ticket.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class MaintenanceDispatchInput(BaseModel):
    """Input payload for dispatching emergency roadside mobile reefer technician."""

    model_config = ConfigDict(extra="ignore")

    truck_id: str = Field(..., description="Power unit identifier")
    latitude: float = Field(..., description="Current vehicle latitude")
    longitude: float = Field(..., description="Current vehicle longitude")
    alarm_code: Optional[str] = Field(default=None, description="Controller alarm code")
    physical_observations_summary: str = Field(..., description="Summary of on-site driver observations")


class MaintenanceDispatchOutput(BaseModel):
    """Result of roadside maintenance ticket creation."""

    model_config = ConfigDict(extra="ignore")

    ticket_id: Optional[str] = Field(default=None, description="Assigned maintenance service ticket ID")
    dispatch_status: str = Field(..., description="Dispatch status: e.g. DISPATCHED, EN_ROUTE")
    estimated_tech_arrival_minutes: int = Field(default=45, description="Estimated technician travel time")
    error: Optional[str] = Field(default=None, description="Error message if dispatch failed")
