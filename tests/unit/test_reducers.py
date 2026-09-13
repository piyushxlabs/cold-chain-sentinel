"""Unit tests for SentinelState reducers and one-way override latch.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Section 4 Step 3 & Section 9.2.
"""

import pytest

from src.state.exceptions import StateValidationError
from src.state.reducers import (
    reduce_append_list,
    reduce_immutable,
    reduce_last_write_wins,
    reduce_merge_dict,
    reduce_monotonic_or,
)


def test_monotonic_or_one_way_latch():
    """Verify requires_immediate_human_override is a strict monotonic-OR latch.

    Once set to True, it must NEVER be reset to False by any downstream node.
    """
    # Initial False stays False if next write is False
    assert reduce_monotonic_or(False, False) is False
    assert reduce_monotonic_or(None, False) is False

    # Setting True activates override
    assert reduce_monotonic_or(False, True) is True
    assert reduce_monotonic_or(None, True) is True

    # CRITICAL: If current is True, any later False write MUST NOT reset the latch
    assert reduce_monotonic_or(True, False) is True

    # True + True stays True
    assert reduce_monotonic_or(True, True) is True


def test_immutable_after_init():
    """Verify entry fields and config cannot be mutated after initial write."""
    # First write (from None to initial value) is permitted
    assert reduce_immutable(None, "evt_9981") == "evt_9981"
    assert reduce_immutable(None, 45) == 45

    # Idempotent write with identical value is permitted
    assert reduce_immutable("evt_9981", "evt_9981") == "evt_9981"
    assert reduce_immutable(45, 45) == 45

    # None update does not clobber existing value
    assert reduce_immutable("evt_9981", None) == "evt_9981"

    # Mutating to a different value MUST raise StateValidationError
    with pytest.raises(StateValidationError) as exc_info:
        reduce_immutable("evt_9981", "evt_DIFFERENT")
    assert "Immutable field violation" in str(exc_info.value)

    with pytest.raises(StateValidationError):
        reduce_immutable("+12065550198", "+12065559999")


def test_append_list():
    """Verify append-only reducer accumulates history without dropping records."""
    assert reduce_append_list(None, ["reason_1"]) == ["reason_1"]
    assert reduce_append_list(["reason_1"], ["reason_2"]) == ["reason_1", "reason_2"]
    assert reduce_append_list(["reason_1", "reason_2"], []) == ["reason_1", "reason_2"]
    assert reduce_append_list([], ["reason_1"]) == ["reason_1"]


def test_merge_dict():
    """Verify merge-by-key reducer merges tool artifacts by tool_call_id."""
    initial = {"call_1": {"status": "SUCCESS"}}
    update = {"call_2": {"status": "FAILED"}}
    merged = reduce_merge_dict(initial, update)

    assert "call_1" in merged
    assert "call_2" in merged
    assert merged["call_1"]["status"] == "SUCCESS"
    assert merged["call_2"]["status"] == "FAILED"

    # Overwrite same key updates that specific key
    overwrite = {"call_1": {"status": "UPDATED"}}
    re_merged = reduce_merge_dict(merged, overwrite)
    assert re_merged["call_1"]["status"] == "UPDATED"
    assert re_merged["call_2"]["status"] == "FAILED"


def test_last_write_wins():
    """Verify last-write-wins updates to the latest non-None value."""
    assert reduce_last_write_wins(None, "first_val") == "first_val"
    assert reduce_last_write_wins("first_val", "second_val") == "second_val"
    assert reduce_last_write_wins("first_val", None) == "first_val"
