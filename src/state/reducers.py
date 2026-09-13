"""State reducers for Cold Chain Sentinel LangGraph StateGraph.

Authoritative specification: DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 3.
"""

from __future__ import annotations

from typing import Any, TypeVar

from src.state.exceptions import StateValidationError

T = TypeVar("T")


def reduce_immutable(current_val: T | None, new_val: T | None) -> T | None:
    """Reducer: immutable-after-init.

    Allows initialization from None or empty uninitialized default channel to a value.
    Once set, any attempt to overwrite with a differing value raises StateValidationError
    to preserve audit integrity.
    """
    if current_val is None or current_val == "":
        return new_val
    if new_val is None or new_val == "":
        return current_val
    if current_val != new_val:
        raise StateValidationError(
            f"Immutable field violation: attempted to mutate '{current_val}' to '{new_val}'"
        )
    return current_val


def reduce_monotonic_or(current_val: bool | None, new_val: bool | None) -> bool:
    """Reducer: monotonic-OR.

    Used strictly for `requires_immediate_human_override`.
    Once set to True by any node, it can NEVER be reset to False by any later node.
    """
    curr = bool(current_val) if current_val is not None else False
    new = bool(new_val) if new_val is not None else False
    return curr or new


def reduce_append_list(current_val: list[T] | None, new_val: list[T] | None) -> list[T]:
    """Reducer: append-only.

    Used for audit_trail, error_logs, and escalation_reasons.
    Appends new elements to the existing list without dropping history.
    """
    curr = list(current_val) if current_val is not None else []
    new = list(new_val) if new_val is not None else []
    return curr + new


def reduce_merge_dict(current_val: dict[str, T] | None, new_val: dict[str, T] | None) -> dict[str, T]:
    """Reducer: merge-by-key.

    Used for tool_artifacts, keyed by tool_call_id.
    Merges dictionary entries so multiple tools can write artifacts without clobbering.
    """
    curr = dict(current_val) if current_val is not None else {}
    new = dict(new_val) if new_val is not None else {}
    return {**curr, **new}


def reduce_last_write_wins(current_val: T | None, new_val: T | None) -> T | None:
    """Reducer: last-write-wins.

    Used for single-writer fields (tms_verified, compliance_review, agreed_action, disposition).
    """
    return new_val if new_val is not None else current_val
