"""Tool Client: sms_send_confirmation.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
import httpx

from src.state.exceptions import StateValidationError, ToolExecutionError
from src.tools.schemas.sms_send_confirmation import SMSSendInput, SMSSendOutput
from src.utils.sanitization import validate_e164_phone


async def sms_send_confirmation(input_data: SMSSendInput) -> SMSSendOutput:
    """Send automated SMS confirmation to driver with dock assignment or service details."""
    if not validate_e164_phone(input_data.recipient_phone_e164):
        raise StateValidationError(
            f"Invalid recipient phone format: '{input_data.recipient_phone_e164}'. Must match strict E.164."
        )

    base_url = os.getenv("SMS_NOTIFICATION_BASE_URL", "https://sms.internal.fleet/api/v1")
    api_key = os.getenv("SMS_NOTIFICATION_API_KEY", "mock_sms_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return SMSSendOutput(
            sms_sent=True,
            provider_message_id="msg_carrier_sms_991823",
        )

    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/send",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return SMSSendOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"SMS delivery failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
