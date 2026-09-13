"""Tool Client: ops_alert_escalate.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
import httpx

from src.state.exceptions import ToolExecutionError
from src.tools.schemas.ops_alert_escalate import OpsAlertInput, OpsAlertOutput


async def ops_alert_escalate(input_data: OpsAlertInput) -> OpsAlertOutput:
    """Trigger one-way P0 operations dispatch alert for human intervention."""
    base_url = os.getenv("OPS_ALERT_BASE_URL", "https://alerts.internal.fleet/api/v1")
    api_key = os.getenv("OPS_ALERT_API_KEY", "mock_ops_alert_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return OpsAlertOutput(
            alert_id="alrt_ops_p0_88921",
            delivered=True,
            channel="OPS_PAGER_P0",
        )

    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/escalate",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return OpsAlertOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"Ops alert delivery failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
