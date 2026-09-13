"""Unit tests for ComplianceReviewDecision schema and compliance_review utilities."""

import pytest
from pydantic import ValidationError

from src.agents.compliance_review import (
    build_evaluation_prompt,
    get_genai_client,
    validate_citation_grounding,
)
from src.state.schema import (
    CallEvidence,
    CargoManifest,
    Coordinates,
    PhysicalObservations,
    RuntimeConfig,
    SentinelState,
)
from src.tools.schemas.compliance_review_decision import ComplianceReviewDecision


def test_compliance_review_decision_valid():
    """Verify valid ComplianceReviewDecision constructs and serializes correctly."""
    decision = ComplianceReviewDecision(
        claim_risk_level="MODERATE",
        review_confidence=0.88,
        suspected_injection=False,
        injection_evidence_note=None,
        reviewer_model="gemini-3.5-flash",
        reasoning_summary="Bulkhead obstruction per physical_observations.air_bulkhead_obstructed with valid HOS.",
    )
    assert decision.claim_risk_level == "MODERATE"
    assert decision.review_confidence == 0.88
    assert decision.suspected_injection is False
    assert decision.reviewer_model == "gemini-3.5-flash"


def test_compliance_review_decision_confidence_bounds():
    """Verify confidence score is strictly bounded within [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        ComplianceReviewDecision(
            claim_risk_level="LOW",
            review_confidence=1.5,  # Invalid: > 1.0
            suspected_injection=False,
            reviewer_model="gemini-3.5-flash",
            reasoning_summary="Valid summary citing physical_observations.",
        )

    with pytest.raises(ValidationError):
        ComplianceReviewDecision(
            claim_risk_level="LOW",
            review_confidence=-0.1,  # Invalid: < 0.0
            suspected_injection=False,
            reviewer_model="gemini-3.5-flash",
            reasoning_summary="Valid summary citing physical_observations.",
        )


def test_compliance_review_decision_invalid_risk_level():
    """Verify claim_risk_level must be one of LOW, MODERATE, HIGH."""
    with pytest.raises(ValidationError):
        ComplianceReviewDecision(
            claim_risk_level="EXTREME",  # Invalid enum value
            review_confidence=0.8,
            suspected_injection=False,
            reviewer_model="gemini-3.5-flash",
            reasoning_summary="Summary citing physical_observations.",
        )


def test_citation_grounding_validation():
    """Verify citation validation enforces field references."""
    grounded_summary = (
        "Cargo sweating detected per physical_observations.cargo_sweating_detected with intact product."
    )
    assert validate_citation_grounding(grounded_summary) is True

    ungrounded_summary = "The driver says the truck feels warm and he wants to take a break."
    assert validate_citation_grounding(ungrounded_summary) is False


def test_build_evaluation_prompt():
    """Verify XML-delimited evaluation prompt construction."""
    mock_state: SentinelState = {
        "event_id": "evt_test_01",
        "cargo_manifest": CargoManifest(
            bol_number="BOL-9901",
            commodity_type="Biologics",
            min_temp_f=34.0,
            max_temp_f=38.0,
            max_allowable_excursion_minutes=45,
            shipper_name="BioPharma Global",
        ),
        "physical_observations": PhysicalObservations(
            air_bulkhead_obstructed=True,
            cargo_sweating_detected=False,
            evaporator_ice_detected=False,
            display_error_codes=["ERR-04"],
            fuel_level_sufficient=True,
            driver_action_taken="Cleared boxes from front bulkhead",
        ),
        "driver_hos_minutes_remaining": 55,
        "eld_hos_minutes_at_dispatch": 62,
        "call_evidence": CallEvidence(
            transcript_or_evidence_ref="evd_ref_001",
            completion_confidence=0.92,
            task_completed=True,
            call_duration_seconds=114,
        ),
    }

    prompt = build_evaluation_prompt(mock_state)
    assert "<evaluation_input>" in prompt
    assert "<cargo_manifest>" in prompt
    assert "BOL-9901" in prompt
    assert "Biologics" in prompt
    assert "driver_hos_minutes_remaining" in prompt
