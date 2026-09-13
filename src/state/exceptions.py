"""Custom exception hierarchy for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Section 3 & 4.
"""

from __future__ import annotations


class AgentError(Exception):
    """Base exception class for all Cold Chain Sentinel agent errors."""

    def __init__(self, message: str, incident_context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.incident_context = incident_context or {}


class StateValidationError(AgentError):
    """Raised when an immutable state field is mutated or invalid state transitions occur."""


class ToolExecutionError(AgentError):
    """Raised when an external capability or telephony tool call fails after retry budget."""


class CallEAttemptExhaustedError(AgentError):
    """Raised when the single-attempt CALL-E interrogation drops, fails, or returns non-completed."""
