"""Unit tests for LangGraph checkpointing backend.

Authoritative specification: DOCS/AGENT_MASTER_PLAN.md Section 4 Step 4 & Section 9.2.
"""

import os
import pytest
from langgraph.graph import StateGraph

from src.state.checkpointing import (
    get_async_checkpointer,
    get_checkpointer,
    get_sqlite_path,
)
from src.state.schema import SentinelState


def test_sqlite_path_creation(tmp_path, monkeypatch):
    """Verify SQLite database directory is automatically created if absent."""
    test_db = tmp_path / "test_data" / "sub" / "checkpoints.sqlite"
    monkeypatch.setenv("SQLITE_CHECKPOINT_PATH", str(test_db))

    path = get_sqlite_path()
    assert os.path.exists(os.path.dirname(path))
    assert path == str(test_db.resolve())


def test_memory_checkpointer_round_trip():
    """Verify write, read, and resume round-trip on Memory checkpointer."""
    with get_checkpointer("memory") as checkpointer:
        # Build a minimal test graph
        builder = StateGraph(SentinelState)
        builder.add_node("step_one", lambda s: {"tms_verified": True, "driver_name": "Marcus Vance"})
        builder.set_entry_point("step_one")
        builder.set_finish_point("step_one")

        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "evt_test_mem_01"}}
        result = graph.invoke({"event_id": "evt_test_mem_01"}, config=config)

        assert result["tms_verified"] is True
        assert result["driver_name"] == "Marcus Vance"

        # Resume state from checkpoint
        checkpoint_state = graph.get_state(config)
        assert checkpoint_state.values["tms_verified"] is True
        assert checkpoint_state.values["driver_name"] == "Marcus Vance"


def test_sqlite_checkpointer_round_trip(tmp_path, monkeypatch):
    """Verify write, read, and resume round-trip on SQLite checkpointer."""
    test_db = tmp_path / "checkpoints.sqlite"
    monkeypatch.setenv("SQLITE_CHECKPOINT_PATH", str(test_db))

    with get_checkpointer("sqlite") as checkpointer:
        builder = StateGraph(SentinelState)
        builder.add_node("step_one", lambda s: {"tms_verified": True, "truck_id": "TRK-880"})
        builder.set_entry_point("step_one")
        builder.set_finish_point("step_one")

        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "evt_test_sqlite_01"}}
        result = graph.invoke({"event_id": "evt_test_sqlite_01"}, config=config)

        assert result["tms_verified"] is True
        assert result["truck_id"] == "TRK-880"

        # Verify state rehydrates
        saved_state = graph.get_state(config)
        assert saved_state.values["truck_id"] == "TRK-880"


@pytest.mark.asyncio
async def test_async_sqlite_checkpointer_round_trip(tmp_path, monkeypatch):
    """Verify non-blocking async SQLite checkpointer write and read."""
    test_db = tmp_path / "async_checkpoints.sqlite"
    monkeypatch.setenv("SQLITE_CHECKPOINT_PATH", str(test_db))

    async with get_async_checkpointer("sqlite") as checkpointer:
        builder = StateGraph(SentinelState)
        builder.add_node("step_one", lambda s: {"tms_verified": True, "nearest_verified_cold_hub": "ColdHub Alpha"})
        builder.set_entry_point("step_one")
        builder.set_finish_point("step_one")

        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "evt_test_async_01"}}
        result = await graph.ainvoke({"event_id": "evt_test_async_01"}, config=config)

        assert result["tms_verified"] is True
        assert result["nearest_verified_cold_hub"] == "ColdHub Alpha"

        saved_state = await graph.aget_state(config)
        assert saved_state.values["nearest_verified_cold_hub"] == "ColdHub Alpha"


def test_unsupported_backend():
    """Verify unsupported backend raises descriptive ValueError."""
    with pytest.raises(ValueError) as exc_info:
        with get_checkpointer("redis"):
            pass
    assert "Unsupported checkpoint backend: 'redis'" in str(exc_info.value)
