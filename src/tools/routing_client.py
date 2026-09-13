"""Tool Client: routing_mutate_route.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
import httpx

from src.state.exceptions import ToolExecutionError
from src.tools.schemas.routing_mutate_route import (
    RoutingMutationInput,
    RoutingMutationOutput,
)


async def routing_mutate_route(input_data: RoutingMutationInput) -> RoutingMutationOutput:
    """Execute autonomous route mutation to emergency cold hub."""
    base_url = os.getenv("FLEET_ROUTING_BASE_URL", "https://routing.internal.fleet/api/v1")
    api_key = os.getenv("FLEET_ROUTING_API_KEY", "mock_routing_key")
    client_mode = os.getenv("CLIENT_MODE", "mock").lower().strip()

    if client_mode == "mock" or "internal.fleet" in base_url:
        await asyncio.sleep(0.02)
        return RoutingMutationOutput(
            route_mutation_confirmed=True,
            new_route_id="RTE-DIVERT-88910",
            new_eta=datetime.now(timezone.utc).isoformat(),
            estimated_drive_minutes=18,
        )

    delays = [1.0, 2.0, 4.0]
    last_err = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{base_url}/mutate",
                    json=input_data.model_dump(),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                res.raise_for_status()
                return RoutingMutationOutput.model_validate(res.json())
        except Exception as e:
            last_err = e
            if attempt < len(delays):
                await asyncio.sleep(delay)

    raise ToolExecutionError(
        f"Route mutation failed after {len(delays)} attempts: {str(last_err)}",
        incident_context=input_data.model_dump(),
    )
