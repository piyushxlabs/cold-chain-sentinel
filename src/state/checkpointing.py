"""Checkpointing backend loader for Cold Chain Sentinel.

Authoritative specification: DOCS/AGENT_ORCHESTRATION_BLUEPRINT.md Section 7.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def get_checkpoint_backend() -> str:
    """Retrieve configured checkpoint backend from environment.

    Returns:
        str: 'sqlite' (dev/local), 'postgres' (prod), or 'memory' (testing).
    """
    return os.getenv("CHECKPOINT_BACKEND", "sqlite").lower().strip()


def get_sqlite_path() -> str:
    """Retrieve SQLite checkpoint database path and ensure directory exists.

    Returns:
        str: Absolute path to SQLite checkpoint database file.
    """
    db_path = os.getenv("SQLITE_CHECKPOINT_PATH", "./data/checkpoints.sqlite")
    abs_path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    return abs_path


@contextmanager
def get_checkpointer(
    backend: str | None = None,
) -> Generator[BaseCheckpointSaver, None, None]:
    """Synchronous context manager providing a configured LangGraph checkpointer.

    Args:
        backend: Optional override for checkpoint backend ('sqlite', 'postgres', 'memory').

    Yields:
        BaseCheckpointSaver: Configured checkpointer instance.
    """
    selected_backend = (backend or get_checkpoint_backend()).lower()

    if selected_backend == "sqlite":
        db_path = get_sqlite_path()
        with SqliteSaver.from_conn_string(db_path) as saver:
            saver.setup()
            yield saver

    elif selected_backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        conn_str = os.getenv("POSTGRES_CONNECTION_STRING")
        if not conn_str:
            raise ValueError("POSTGRES_CONNECTION_STRING is required when CHECKPOINT_BACKEND=postgres")
        with PostgresSaver.from_conn_string(conn_str) as saver:
            saver.setup()
            yield saver

    elif selected_backend == "memory":
        saver = MemorySaver()
        yield saver

    else:
        raise ValueError(
            f"Unsupported checkpoint backend: '{selected_backend}'. Expected 'sqlite', 'postgres', or 'memory'."
        )


@asynccontextmanager
async def get_async_checkpointer(
    backend: str | None = None,
) -> AsyncGenerator[BaseCheckpointSaver, None]:
    """Asynchronous context manager providing a configured async LangGraph checkpointer.

    Args:
        backend: Optional override for checkpoint backend ('sqlite', 'postgres', 'memory').

    Yields:
        BaseCheckpointSaver: Configured async checkpointer instance.
    """
    selected_backend = (backend or get_checkpoint_backend()).lower()

    if selected_backend == "sqlite":
        db_path = get_sqlite_path()
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            await saver.setup()
            yield saver

    elif selected_backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        conn_str = os.getenv("POSTGRES_CONNECTION_STRING")
        if not conn_str:
            raise ValueError("POSTGRES_CONNECTION_STRING is required when CHECKPOINT_BACKEND=postgres")
        async with AsyncPostgresSaver.from_conn_string(conn_str) as saver:
            await saver.setup()
            yield saver

    elif selected_backend == "memory":
        saver = MemorySaver()
        yield saver

    else:
        raise ValueError(
            f"Unsupported checkpoint backend: '{selected_backend}'. Expected 'sqlite', 'postgres', or 'memory'."
        )
