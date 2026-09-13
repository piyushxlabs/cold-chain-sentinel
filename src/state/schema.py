"""SentinelState schema definitions for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    """Geographical coordinates for truck and hubs."""

    model_config = ConfigDict(extra="ignore")

    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")


class CargoManifest(BaseModel):
    """Cargo BOL and biological/pharmaceutical constraints."""

    model_config = ConfigDict(extra="ignore")

    bol_number: str = Field(..., description="Bill of Lading identifier")
    commodity_type: Literal["Biologics", "Pharma", "Produce", "Dairy", "Meat", "Frozen", "Other"] = (
        Field(..., description="Cargo classification")
    )
    min_temp_f: float = Field(..., description="Minimum allowable temperature in Fahrenheit")
    max_temp_f: float = Field(..., description="Maximum allowable temperature in Fahrenheit")
    max_allowable_excursion_minutes: int = Field(
        ..., description="Maximum continuous excursion minutes permitted before total loss"
    )
    shipper_name: str = Field(..., description="Shipper enterprise name")


class PhysicalObservations(BaseModel):
    """Driver physical check observations reported during CALL-E triage."""

    model_config = ConfigDict(extra="ignore")

    air_bulkhead_obstructed: bool = Field(..., description="Whether cargo is blocking the return air bulkhead")
    cargo_sweating_detected: bool = Field(..., description="Condensation or moisture detected on pallets/cases")
    evaporator_ice_detected: bool = Field(..., description="Visual frost/ice on reefer evaporator coils")
    display_error_codes: list[str] = Field(default_factory=list, description="Error codes on the unit controller")
    fuel_level_sufficient: bool = Field(..., description="Whether diesel reefer fuel is above minimum threshold")
    driver_action_taken: str = Field(..., description="Summary of manual actions driver executed on-site")


class CallEvidence(BaseModel):
    """CALL-E telephony execution evidence and confidence signals."""

    model_config = ConfigDict(extra="ignore")

    transcript_or_evidence_ref: str = Field(..., description="Reference link or sanitized excerpt of the call")
    completion_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from CALL-E outcome")
    task_completed: bool = Field(..., description="Whether telephony checklist completed successfully")
    call_duration_seconds: int = Field(..., description="Duration of telephone connection in seconds")


class ComplianceReview(BaseModel):
    """Google Gemini cognitive review of driver observations and cargo risk."""

    model_config = ConfigDict(extra="ignore")

    claim_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        ..., description="Assessed risk of cargo damage or liability"
    )
    review_confidence: float = Field(..., ge=0.0, le=1.0, description="Model evaluation confidence score")
    suspected_injection: bool = Field(
        ..., description="Whether driver speech contained prompt injection or scope redirection"
    )
    reviewer_model: str = Field(..., description="Gemini model identifier used for evaluation")
    reasoning_summary: str = Field(..., description="Field-grounded rationale for risk decision")
    injection_evidence_note: str | None = Field(
        default=None, description="Detailed explanation if injection or anomaly was suspected"
    )


AgreedAction = Literal[
    "CONTINUE_MONITORED_ROUTE",
    "DIVERT_TO_EMERGENCY_COLD_HUB",
    "PULL_OVER_ROADSIDE_SERVICE",
    "DRIVER_REFUSED",
    "ESCALATE_TO_HUMAN_DISPATCH",
]

Disposition = Literal[
    "AUTONOMOUSLY_DIVERTED",
    "AUTONOMOUSLY_RESOLVED_CONTINUE",
    "AUTONOMOUSLY_SERVICED",
    "ESCALATED_HOS_BREACH",
    "ESCALATED_CARGO_SPOILAGE_RISK",
    "ESCALATED_TELEPHONY_FAILURE",
    "ESCALATED_INJECTION_DETECTED",
    "ESCALATED_DRIVER_REFUSAL",
    "ESCALATED_MANUAL_OVERRIDE",
]


class AuditEvent(BaseModel):
    """Immutable audit event for FSMA compliance."""

    model_config = ConfigDict(extra="ignore")

    event_type: str
    node_name: str
    timestamp: str
    details: dict[str, Any]


class ErrorRecord(BaseModel):
    """Structured error log entry."""

    model_config = ConfigDict(extra="ignore")

    node_name: str
    error_type: str
    message: str
    timestamp: str
    retry_count: int = 0


class ToolCallResult(BaseModel):
    """Result of an internal fleet capability or external telephony tool invocation."""

    model_config = ConfigDict(extra="ignore")

    tool_call_id: str
    tool_name: str
    status: Literal["SUCCESS", "FAILED", "SKIPPED"]
    payload: dict[str, Any]
    timestamp: str
    latency_ms: float


class RuntimeConfig(BaseModel):
    """Immutable execution configuration set at ingress."""

    model_config = ConfigDict(extra="ignore")

    trace_id: str = Field(..., description="Distributed tracing identifier")
    client_mode: Literal["mock", "live"] = Field("mock", description="Telephony mode: mock or live")
    max_tool_retry_attempts: int = Field(3, description="Maximum retries for transient tool calls")
    min_hos_minutes_for_reroute: int = Field(35, description="Minimum HOS minutes required for autonomous divert")


class SentinelState(TypedDict, total=False):
    """LangGraph StateGraph typed dictionary representation for Cold Chain Sentinel."""

    # Entry fields (immutable-after-init)
    event_id: str
    session_id: str
    timestamp: str | datetime
    truck_id: str
    trailer_id: str
    current_temp_f: float
    setpoint_temp_f: float
    temp_differential_f: float
    duration_minutes: int
    telematics_alarm_code: str
    current_coordinates: Coordinates
    target_destination: str
    origin: str
    cargo_manifest: CargoManifest
    driver_phone_e164: str
    driver_name: str
    driver_locale: str

    # Enrichment fields (written by enrichment node)
    tms_verified: bool
    eld_hos_minutes_at_dispatch: int | None
    nearest_verified_cold_hub: str | None

    # Call session fields (written by call_interrogation node)
    call_id: str | None
    call_status: Literal["completed", "busy", "no_answer", "failed", "pending"] | None
    driver_contacted: bool
    driver_reported_alarm_code: str | None
    physical_observations: PhysicalObservations | None
    driver_hos_minutes_remaining: int | None
    call_evidence: CallEvidence | None

    # Compliance review fields (written by compliance_review node)
    compliance_review: ComplianceReview | None

    # Decision fields (written by decision_gate node)
    agreed_action: AgreedAction | None
    disposition: Disposition | None
    requires_immediate_human_override: bool
    escalation_reasons: list[str]

    # Cross-cutting fields (written across nodes)
    audit_trail: list[AuditEvent]
    error_logs: list[ErrorRecord]
    tool_artifacts: dict[str, ToolCallResult]

    # Terminal deliverable fields (assembled by persistence_audit node)
    execution_timestamp: datetime | None

    # Config (immutable-after-init)
    config: RuntimeConfig
