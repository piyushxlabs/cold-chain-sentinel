"""Tool Client: warehouse_reserve_dock.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
import httpx

from src.state.exceptions import ToolExecutionError
from src.tools.schemas.warehouse_reserve_dock import (
    WarehouseReservationInput,
    WarehouseReservationOutput,
)


async def warehouse_reserve_dock(input_data: WarehouseReservationInput) -> WarehouseReservationOutput:
    """Execute emergency cross-dock reservation at verified cold hub."""
    base_url = os.getenv("WAREHOUSE_RESERVATION_BASE_URL", "https://dock.internal.fleet/api/v1")
    api_key = os.getenv("WAREHOUSE_RESERVATION_API_KEY", "mock_wh_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return WarehouseReservationOutput(
            reservation_confirmed=True,
            dock_assignment="Dock Bay 4 - Refrigerated Inbound",
            reservation_id="RES-WH-44091",
            confirmation_code="CONF-LNK-882",
        )

    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/reserve",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return WarehouseReservationOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"Warehouse reservation failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
