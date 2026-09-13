"""LangGraph StateGraph orchestration graph for Cold Chain Sentinel.

Authoritative specifications:
- DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 4, Section 5
- DOCS/AGENT_LOGIC_SPEC.md Section 6
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.autonomous_actuation import autonomous_actuation_node
from src.agents.call_interrogation import call_interrogation_node
from src.agents.compliance_review import compliance_review_node
from src.agents.decision_gate import decision_gate_node
from src.agents.enrichment import enrichment_node
from src.agents.escalation_failure import escalation_failure_node
from src.agents.ingress import ingress_node
from src.agents.persistence_audit import persistence_audit_node
from src.state.schema import SentinelState


def route_after_enrichment(state: SentinelState) -> Literal["call_interrogation", "escalation_failure"]:
    """Conditional routing edge following TMS and ELD enrichment."""
    if state.get("requires_immediate_human_override", False) or not state.get("tms_verified", False):
        return "escalation_failure"
    return "call_interrogation"


def route_after_call(state: SentinelState) -> Literal["compliance_review", "escalation_failure"]:
    """Conditional routing edge following CALL-E driver interrogation."""
    status = state.get("call_status")
    override = state.get("requires_immediate_human_override", False)
    if override or status != "completed":
        return "escalation_failure"
    return "compliance_review"


def route_after_decision_gate(state: SentinelState) -> Literal["autonomous_actuation", "escalation_failure"]:
    """Conditional routing edge following deterministic Decision Gate evaluation."""
    override = state.get("requires_immediate_human_override", False)
    action = state.get("agreed_action")

    if override or action in ["ESCALATE_TO_HUMAN_DISPATCH", "DRIVER_REFUSED"]:
        return "escalation_failure"
    return "autonomous_actuation"


def create_sentinel_graph() -> StateGraph:
    """Construct the uncompiled 8-node LangGraph StateGraph topology.

    Topology:
    ingress -> enrichment -> [call_interrogation | escalation_failure]
    call_interrogation -> [compliance_review | escalation_failure]
    compliance_review -> decision_gate
    decision_gate -> [autonomous_actuation | escalation_failure]
    autonomous_actuation -> persistence_audit -> END
    escalation_failure -> persistence_audit -> END
    """
    workflow = StateGraph(SentinelState)

    # 1. Add all 8 nodes
    workflow.add_node("ingress", ingress_node)
    workflow.add_node("enrichment", enrichment_node)
    workflow.add_node("call_interrogation", call_interrogation_node)
    workflow.add_node("compliance_review", compliance_review_node)
    workflow.add_node("decision_gate", decision_gate_node)
    workflow.add_node("autonomous_actuation", autonomous_actuation_node)
    workflow.add_node("escalation_failure", escalation_failure_node)
    workflow.add_node("persistence_audit", persistence_audit_node)

    # 2. Set entry point
    workflow.set_entry_point("ingress")

    # 3. Add deterministic edges
    workflow.add_edge("ingress", "enrichment")
    workflow.add_edge("compliance_review", "decision_gate")
    workflow.add_edge("autonomous_actuation", "persistence_audit")
    workflow.add_edge("escalation_failure", "persistence_audit")
    workflow.add_edge("persistence_audit", END)

    # 4. Add conditional edges
    workflow.add_conditional_edges(
        "enrichment",
        route_after_enrichment,
        {
            "call_interrogation": "call_interrogation",
            "escalation_failure": "escalation_failure",
        },
    )

    workflow.add_conditional_edges(
        "call_interrogation",
        route_after_call,
        {
            "compliance_review": "compliance_review",
            "escalation_failure": "escalation_failure",
        },
    )

    workflow.add_conditional_edges(
        "decision_gate",
        route_after_decision_gate,
        {
            "autonomous_actuation": "autonomous_actuation",
            "escalation_failure": "escalation_failure",
        },
    )

    return workflow


def build_sentinel_graph(checkpointer: Any = None) -> CompiledStateGraph:
    """Build and compile the Sentinel StateGraph with optional checkpointer."""
    workflow = create_sentinel_graph()
    return workflow.compile(checkpointer=checkpointer)


# Module-level StateGraph builder
sentinel_workflow = create_sentinel_graph()
