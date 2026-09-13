"""Tool Client: maintenance_dispatch_ticket.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
import httpx

from src.state.exceptions import ToolExecutionError
from src.tools.schemas.maintenance_dispatch_ticket import (
    MaintenanceDispatchInput,
    MaintenanceDispatchOutput,
)


async def maintenance_dispatch_ticket(input_data: MaintenanceDispatchInput) -> MaintenanceDispatchOutput:
    """Dispatch emergency roadside mobile reefer service technician."""
    base_url = os.getenv("MAINTENANCE_DISPATCH_BASE_URL", "https://maintenance.internal.fleet/api/v1")
    api_key = os.getenv("MAINTENANCE_DISPATCH_API_KEY", "mock_maint_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return MaintenanceDispatchOutput(
            ticket_id="TCK-ROADSIDE-7712",
            dispatch_status="DISPATCHED_MOBILE_UNIT",
            estimated_tech_arrival_minutes=35,
        )

    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/ticket",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return MaintenanceDispatchOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"Maintenance dispatch failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
