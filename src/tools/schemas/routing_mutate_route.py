"""Tool Schema: routing_mutate_route.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RoutingMutationInput(BaseModel):
    """Input payload for dispatching route mutation to emergency cold hub."""

    model_config = ConfigDict(extra="ignore")

    truck_id: str = Field(..., description="Target commercial power unit")
    destination_hub_name: str = Field(..., description="Name of destination cold hub")
    destination_lat: float = Field(..., description="Latitude coordinate")
    destination_lon: float = Field(..., description="Longitude coordinate")


class RoutingMutationOutput(BaseModel):
    """Result of autonomous route mutation dispatch."""

    model_config = ConfigDict(extra="ignore")

    route_mutation_confirmed: bool = Field(..., description="Whether fleet routing system accepted route mutation")
    new_route_id: Optional[str] = Field(default=None, description="Assigned new navigation route identifier")
    new_eta: Optional[str] = Field(default=None, description="Updated Estimated Time of Arrival at destination")
    estimated_drive_minutes: int = Field(default=0, description="Drive time in minutes to destination")
    error: Optional[str] = Field(default=None, description="Error message if mutation failed")
