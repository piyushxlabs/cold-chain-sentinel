"""Tool Schema: eld_lookup_hos_minutes.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ELDLookupInput(BaseModel):
    """Input parameters for ELD Hours-of-Service query."""

    model_config = ConfigDict(extra="ignore")

    truck_id: str = Field(..., description="Power unit identifier")
    driver_phone_e164: str = Field(..., description="Driver phone number for driver identification")


class ELDLookupOutput(BaseModel):
    """Result of ELD HOS query captured at dispatch."""

    model_config = ConfigDict(extra="ignore")

    hos_minutes_remaining: int = Field(..., description="Recorded available driving minutes remaining")
    as_of_timestamp: str = Field(..., description="Timestamp when ELD record was sampled")
    error: Optional[str] = Field(default=None, description="Error message if ELD lookup failed")
