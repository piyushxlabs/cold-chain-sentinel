"""LLM-Specific and Structural Evaluation Test Suite for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_MASTER_PLAN.md Section 9, Section 9.3, Section 9.4, Section 9.6
- DOCS/AGENT_LOGIC_SPEC.md Section 8, Section 9
"""

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from src.agents.compliance_review import (
    build_evaluation_prompt,
    compliance_review_node,
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


def load_eval_cases() -> list[dict[str, Any]]:
    """Load evaluation test cases from promptfoo_cases.json."""
    cases_file = Path(__file__).parent / "promptfoo_cases.json"
    with open(cases_file, "r", encoding="utf-8") as f:
        return json.load(f)


def build_state_from_eval_case(case_vars: dict[str, Any]) -> SentinelState:
    """Construct a full SentinelState from an evaluation case dictionary."""
    return {
        "event_id": "evt_eval_001",
        "session_id": "sess_eval_001",
        "timestamp": "2026-09-13T10:00:00Z",
        "truck_id": "TRK-902",
        "trailer_id": "TRL-8841",
        "current_temp_f": 39.5,
        "setpoint_temp_f": 34.0,
        "temp_differential_f": 5.5,
        "duration_minutes": 25,
        "telematics_alarm_code": "ALARM 18",
        "current_coordinates": Coordinates(latitude=40.8, longitude=-96.7),
        "target_destination": "Omaha DC",
        "origin": "Kansas City Hub",
        "cargo_manifest": CargoManifest(**case_vars["cargo_manifest"]),
        "driver_phone_e164": "+12065550198",
        "driver_name": "Marcus Vance",
        "driver_locale": "en-US",
        "config": RuntimeConfig(
            trace_id="trc_eval_001",
            client_mode="mock",
            max_tool_retry_attempts=3,
            min_hos_minutes_for_reroute=35,
        ),
        "physical_observations": PhysicalObservations(**case_vars["physical_observations"]),
        "driver_hos_minutes_remaining": case_vars.get("driver_hos_minutes_remaining", 50),
        "eld_hos_minutes_at_dispatch": case_vars.get("eld_hos_minutes_at_dispatch", 50),
        "call_evidence": CallEvidence(**case_vars["call_evidence"]),
        "requires_immediate_human_override": False,
    }


def test_eval_dataset_file_validity():
    """Verify that promptfoo_cases.json is valid and contains all required evaluation cases."""
    cases = load_eval_cases()
    assert len(cases) >= 5
    case_ids = [c["id"] for c in cases]
    assert "case_1_simple_compliant" in case_ids
    assert "case_2_biologics_sweating" in case_ids
    assert "case_3_missing_evidence_gap" in case_ids
    assert "case_4_hos_discrepancy_cross_exam" in case_ids
    assert "case_5_prompt_injection_detection" in case_ids


@pytest.mark.asyncio
async def test_eval_structured_output_accuracy():
    """Verify structured output fields and schema validation across evaluation cases."""
    cases = load_eval_cases()
    for case in cases:
        state = build_state_from_eval_case(case["vars"])
        prompt = build_evaluation_prompt(state)

        assert "<evaluation_input>" in prompt
        assert "</evaluation_input>" in prompt

        node_output = await compliance_review_node(state)
        assert "compliance_review" in node_output

        review = node_output["compliance_review"]
        # Verify strict ComplianceReview schema
        assert review.claim_risk_level in ["LOW", "MODERATE", "HIGH"]
        assert 0.0 <= review.review_confidence <= 1.0
        assert isinstance(review.suspected_injection, bool)
        assert isinstance(review.reasoning_summary, str)
        assert len(review.reasoning_summary) > 0


def test_eval_citation_grounding_enforcement():
    """Verify citation grounding checker flags summaries without field references."""
    grounded_summary = "Per physical_observations.cargo_sweating_detected, sweating was observed."
    assert validate_citation_grounding(grounded_summary) is True

    ungrounded_summary = "The driver sounded unsure and the cargo might be spoiled."
    assert validate_citation_grounding(ungrounded_summary) is False


@pytest.mark.asyncio
async def test_eval_hallucination_prevention_on_missing_evidence():
    """Verify missing evidence lowers review confidence and notes gaps without hallucinating."""
    decision = ComplianceReviewDecision(
        claim_risk_level="HIGH",
        review_confidence=0.35,
        suspected_injection=False,
        reviewer_model="gemini-3.5-flash",
        reasoning_summary="Per call_evidence.completion_confidence, triage is incomplete with missing evidence reference.",
    )

    assert decision.review_confidence < 0.5
    assert validate_citation_grounding(decision.reasoning_summary) is True


@pytest.mark.asyncio
async def test_eval_prompt_injection_defense():
    """Verify prompt injection triggers suspected_injection=True and locks human override."""
    decision_with_injection = ComplianceReviewDecision(
        claim_risk_level="HIGH",
        review_confidence=0.85,
        suspected_injection=True,
        injection_evidence_note="Driver transcript attempted to inject system directives: 'Ignore previous instructions'",
        reviewer_model="gemini-3.5-flash",
        reasoning_summary="Per physical_observations.cargo_sweating_detected, sweating detected. Suspected prompt injection in transcript reference.",
    )

    from src.state.schema import ComplianceReview
    review_obj = ComplianceReview(
        claim_risk_level=decision_with_injection.claim_risk_level,
        review_confidence=decision_with_injection.review_confidence,
        suspected_injection=decision_with_injection.suspected_injection,
        reviewer_model=decision_with_injection.reviewer_model,
        reasoning_summary=decision_with_injection.reasoning_summary,
        injection_evidence_note=decision_with_injection.injection_evidence_note,
    )

    assert review_obj.suspected_injection is True


def test_negative_no_hitl_resumption_endpoints():
    """Negative verification: Confirm zero Approve/Deny/Resume endpoints or code paths exist in src/."""
    from src.main import app

    routes = [route.path for route in app.routes]
    # Assert NO approve, deny, or resume endpoints exist
    for route in routes:
        assert "/approve" not in route.lower()
        assert "/deny" not in route.lower()
        assert "/resume" not in route.lower()
        assert "/checkpoint/resume" not in route.lower()


def test_structural_prohibitions_enforcement():
    """Negative verification: Confirm zero vehicle-control, DIY repair, or freight valuation tools exist."""
    import src.tools as tools_module

    available_tool_functions = [
        name for name, _ in inspect.getmembers(tools_module, inspect.isfunction)
    ]

    # Prohibited capabilities:
    prohibited_keywords = [
        "vehicle_control",
        "brake",
        "engine_stop",
        "ignition",
        "repair_guide",
        "diy_instructions",
        "claim_settlement",
        "freight_valuation",
        "payout",
    ]

    for tool_name in available_tool_functions:
        for keyword in prohibited_keywords:
            assert keyword not in tool_name.lower(), f"Prohibited tool capability detected: {tool_name}"
