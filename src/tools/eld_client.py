"""Tool Client: eld_lookup_hos_minutes.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
import httpx

from src.state.exceptions import ToolExecutionError
from src.tools.schemas.eld_lookup_hos_minutes import ELDLookupInput, ELDLookupOutput


async def eld_lookup_hos_minutes(input_data: ELDLookupInput) -> ELDLookupOutput:
    """Retrieve recorded driver HOS minutes at dispatch with exponential retry."""
    base_url = os.getenv("FLEET_ELD_BASE_URL", "https://eld.internal.fleet/api/v1")
    api_key = os.getenv("FLEET_ELD_API_KEY", "mock_eld_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return ELDLookupOutput(
            hos_minutes_remaining=52,
            as_of_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Live ELD execution with exponential backoff (1s, 2s, 4s)
    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/hos",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return ELDLookupOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"ELD lookup failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
