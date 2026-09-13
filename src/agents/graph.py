"""LangGraph StateGraph orchestration graph for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4.
"""

from __future__ import annotations

from langgraph.graph import StateGraph

from src.state.schema import SentinelState


def create_sentinel_graph() -> StateGraph:
    """Initialize the uncompiled LangGraph StateGraph typed to SentinelState.

    In Step 5, this initializes the StateGraph skeleton with zero nodes/edges.
    Full node wiring and conditional edges are added in Step 11.

    Returns:
        StateGraph: Initialized StateGraph instance typed to SentinelState.
    """
    workflow = StateGraph(SentinelState)
    return workflow


# Default module-level StateGraph instance
sentinel_workflow = create_sentinel_graph()
