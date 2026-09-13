"""CALL-E telephony client wrapper with Mock and Live SDK support.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4, DOCS/read.md, DOCS/client.py.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from src.state.exceptions import CallEAttemptExhaustedError, StateValidationError
from src.tools.schemas.call_e_initiate_triage import (
    CallETriageInput,
    CallETriageOutput,
    CallETriageStructuredResult,
)
from src.utils.sanitization import sanitize_interpolated_text, validate_e164_phone


class MockCalleClient:
    """Mock CALL-E client for deterministic local development and automated testing."""

    def __init__(self, api_key: str = "mock_key", base_url: str = "https://mock.heycall-e.com") -> None:
        self.api_key = api_key
        self.base_url = base_url

    async def create_and_wait(
        self,
        task: str,
        result_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Simulate realistic CALL-E telephone conversation turnaround."""
        await asyncio.sleep(0.05)  # Simulate network latency

        return {
            "call_id": "calle_mock_session_001",
            "status": "completed",
            "task_completed": True,
            "completion_confidence": {"score": 0.94, "label": "high"},
            "structured_result": {
                "driver_verified_safe_location": True,
                "reefer_engine_running": True,
                "air_bulkhead_obstructed": True,
                "cargo_sweating_detected": False,
                "evaporator_ice_detected": False,
                "fuel_level_sufficient": True,
                "driver_reported_alarm_code": "ALARM 18 - HIGH ENGINE TEMP",
                "driver_hos_minutes_remaining": 45,
                "selected_option": "DIVERT_TO_COLD_HUB",
                "emergency_reported": False,
                "driver_action_taken": "Parked in rest area, checked bulkhead obstruction",
            },
            "evidence": {
                "transcript_or_evidence_ref": "evd_mock_call_001",
                "call_duration_seconds": 118,
            },
            "error": None,
        }


def extract_confidence_score(confidence_val: Any) -> float:
    """Defensively extract numeric float score from CALL-E confidence object or scalar."""
    if isinstance(confidence_val, (int, float)):
        return max(0.0, min(1.0, float(confidence_val)))
    if isinstance(confidence_val, dict):
        score = confidence_val.get("score", 0.0)
        return max(0.0, min(1.0, float(score)))
    return 0.5


def format_calle_task(phone: str, task_instructions: str) -> str:
    """Format task string matching CALL-E SDK requirement: 'Call {phone} and {task}'."""
    sanitized_instructions = sanitize_interpolated_text(task_instructions)
    return f"Call {phone} and {sanitized_instructions}"


async def call_e_initiate_triage(input_data: CallETriageInput) -> CallETriageOutput:
    """Initiate and await single outbound driver interrogation call via CALL-E.

    Enforces:
    - Strict E.164 phone validation
    - Phone-prefixed task formatting: 'Call {phone} and {task}'
    - Zero-Redial policy (single attempt, no retry)
    - Defensive confidence score extraction
    """
    if not validate_e164_phone(input_data.recipient_phone_e164):
        raise StateValidationError(
            f"Invalid recipient phone format: '{input_data.recipient_phone_e164}'. Must match strict E.164."
        )

    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()
    formatted_task = format_calle_task(input_data.recipient_phone_e164, input_data.task_instructions)

    if client_mode == "live":
        try:
            from calle import CalleClient

            api_key = os.getenv("CALLE_API_KEY")
            base_url = os.getenv("CALLE_BASE_URL", "https://test-api.heycall-e.com")
            if not api_key:
                raise ValueError("Missing CALLE_API_KEY for live telephony mode")

            client = CalleClient(api_key=api_key, base_url=base_url)
            # Run blocking SDK call in worker thread to maintain non-blocking async execution
            raw_response = await asyncio.to_thread(
                client.calls.create_and_wait,
                task=formatted_task,
                result_schema=input_data.result_schema,
            )
        except Exception as e:
            return CallETriageOutput(
                status="failed",
                task_completed=False,
                completion_confidence=0.0,
                error=f"CALL-E SDK invocation failed: {str(e)}",
            )
    else:
        mock_client = MockCalleClient()
        raw_response = await mock_client.create_and_wait(
            task=formatted_task,
            result_schema=input_data.result_schema,
        )

    # Defensively parse output
    status = str(raw_response.get("status", "failed")).lower()
    if status not in ["completed", "busy", "no_answer", "failed", "pending"]:
        status = "failed"

    task_completed = bool(raw_response.get("task_completed", False))
    conf_score = extract_confidence_score(raw_response.get("completion_confidence", 0.0))

    structured_res = None
    if raw_response.get("structured_result"):
        try:
            structured_res = CallETriageStructuredResult.model_validate(raw_response["structured_result"])
        except Exception as err:
            resolved_call_id = raw_response.get("call_id") or raw_response.get("id")
            return CallETriageOutput(
                call_id=resolved_call_id,
                status="failed",
                task_completed=False,
                completion_confidence=conf_score,
                error=f"Malformed structured result schema: {str(err)}",
            )

    resolved_call_id = raw_response.get("call_id") or raw_response.get("id")
    return CallETriageOutput(
        call_id=resolved_call_id,
        status=status,  # type: ignore
        task_completed=task_completed,
        completion_confidence=conf_score,
        structured_result=structured_res,
        evidence=raw_response.get("evidence", {}),
        error=raw_response.get("error"),
    )
