"""Tool Schema: tms_lookup_driver_and_load.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class NearestColdHubCandidate(BaseModel):
    """Pre-verified nearest cold storage facility resolved by TMS."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Facility name")
    address: str = Field(..., description="Physical street address")
    lat: float = Field(..., description="Latitude coordinate")
    lon: float = Field(..., description="Longitude coordinate")
    estimated_drive_minutes: int = Field(..., description="Estimated travel time in minutes")


class TMSLookupInput(BaseModel):
    """Input parameters for TMS driver and load verification."""

    model_config = ConfigDict(extra="ignore")

    truck_id: str = Field(..., description="Power unit identifier")
    trailer_id: str = Field(..., description="Reefer trailer identifier")
    event_id: str = Field(..., description="Telematics excursion event identifier")
    driver_phone_e164: Optional[str] = Field(default=None, description="Incoming driver contact phone in E.164 format")
    driver_name: Optional[str] = Field(default=None, description="Incoming commercial driver full name")


class TMSLookupOutput(BaseModel):
    """Result from fleet TMS lookup."""

    model_config = ConfigDict(extra="ignore")

    tms_verified: bool = Field(..., description="Whether load and driver were successfully verified in TMS")
    driver_phone_e164_confirmed: str = Field(..., description="Verified driver contact phone in E.164 format")
    driver_name: str = Field(..., description="Assigned commercial driver full name")
    driver_locale: str = Field(default="en-US", description="Preferred communication locale")
    bol_number: str = Field(..., description="Active Bill of Lading reference")
    commodity_type: str = Field(..., description="Cargo classification")
    nearest_verified_cold_hub: NearestColdHubCandidate = Field(
        ..., description="Designated emergency cross-dock destination"
    )
    error: Optional[str] = Field(default=None, description="Error message if TMS resolution failed")
