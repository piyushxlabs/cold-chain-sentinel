"""Tool Schema: call_e_initiate_triage.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4 & 5.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class CallETriageStructuredResult(BaseModel):
    """Structured checklist observations returned by CALL-E triage call."""

    model_config = ConfigDict(extra="ignore")

    driver_verified_safe_location: bool = Field(..., description="Whether driver is parked in safe location")
    reefer_engine_running: bool = Field(..., description="Whether diesel reefer unit engine is operational")
    air_bulkhead_obstructed: bool = Field(..., description="Whether cargo blocks return air bulkhead")
    cargo_sweating_detected: bool = Field(..., description="Condensation on product/pallets")
    evaporator_ice_detected: bool = Field(default=False, description="Frost/ice on coils")
    fuel_level_sufficient: bool = Field(default=True, description="Diesel reefer fuel sufficiency")
    driver_reported_alarm_code: Optional[str] = Field(default=None, description="Alarm code displayed on controller")
    driver_hos_minutes_remaining: int = Field(..., description="Hours of Service minutes remaining")
    selected_option: Literal[
        "DIVERT_TO_COLD_HUB",
        "CONTINUE_MONITORED",
        "ROADSIDE_SERVICE",
        "DRIVER_REFUSED",
    ] = Field(..., description="Action agreed upon with the driver")
    emergency_reported: bool = Field(default=False, description="Whether driver reported fire, injury, or crash")
    driver_action_taken: str = Field(default="", description="Actions performed on site")


class CallETriageInput(BaseModel):
    """Input payload for initiating a CALL-E outbound triage telephone call."""

    model_config = ConfigDict(extra="ignore")

    recipient_phone_e164: str = Field(..., description="Target driver phone in E.164 format")
    driver_locale: str = Field("en-US", description="Language/accent locale for call")
    task_instructions: str = Field(..., description="Declarative instructions and constraints for CALL-E agent")
    result_schema: dict[str, Any] = Field(..., description="JSON Schema defining expected structured result")


class CallETriageOutput(BaseModel):
    """Execution output from CALL-E telephony integration."""

    model_config = ConfigDict(extra="ignore")

    call_id: Optional[str] = Field(default=None, description="CALL-E unique call identifier")
    status: Literal["completed", "busy", "no_answer", "failed", "pending"] = Field(
        ..., description="Terminal telephony connection status"
    )
    task_completed: bool = Field(..., description="Whether the interrogation checklist finished successfully")
    completion_confidence: float = Field(..., ge=0.0, le=1.0, description="Telephony extraction confidence score")
    structured_result: Optional[CallETriageStructuredResult] = Field(
        default=None, description="Extracted driver observations"
    )
    evidence: dict[str, Any] = Field(default_factory=dict, description="Call evidence reference metadata")
    error: Optional[str] = Field(default=None, description="Error description if call failed")
