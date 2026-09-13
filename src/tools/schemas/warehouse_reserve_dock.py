"""Tool Schema: warehouse_reserve_dock.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WarehouseReservationInput(BaseModel):
    """Input payload for emergency cross-dock reservation."""

    model_config = ConfigDict(extra="ignore")

    destination_hub_name: str = Field(..., description="Target facility name")
    truck_id: str = Field(..., description="Power unit identifier")
    bol_number: str = Field(..., description="Bill of Lading identifier")
    eta_timestamp: str = Field(..., description="Estimated arrival time ISO timestamp")
    commodity_type: str = Field(..., description="Commodity type requiring refrigerated storage")


class WarehouseReservationOutput(BaseModel):
    """Result of warehouse dock reservation transaction."""

    model_config = ConfigDict(extra="ignore")

    reservation_confirmed: bool = Field(..., description="Whether facility confirmed dock space")
    dock_assignment: Optional[str] = Field(default=None, description="Assigned loading dock bay number")
    reservation_id: Optional[str] = Field(default=None, description="Warehouse reservation reference")
    confirmation_code: Optional[str] = Field(default=None, description="Security check-in confirmation code")
    error: Optional[str] = Field(default=None, description="Error message if reservation failed")
