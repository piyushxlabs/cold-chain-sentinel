"""User feedback to Langfuse telemetry annotation pipeline.

Authoritative specifications:
- DOCS/INTERFACE_OBSERVABILITY_SYSTEM.md Section 7, Section 7a
- DOCS/AGENT_MASTER_PLAN.md Section 8, Section 10 (Step 18)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from src.telemetry.tracing import (
    ensure_session_trace,
    get_langfuse_client,
    get_telemetry_registry,
)


ScoreDataType = Literal["NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT", "CORRECTION"]


def create_score(
    event_id: str,
    name: str,
    value: Any,
    comment: str | None = None,
    span_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a structured quality score on a Langfuse trace or Generation span.

    Supported Score Names per INTERFACE_OBSERVABILITY_SYSTEM.md Section 7a:
    - `user_thumbs`: BOOLEAN (True/False) — Binary judgment on Risk Assessment Card
    - `user_rating`: NUMERIC (1–5) — Star rating on Risk Assessment Card
    - `overall_outcome`: BOOLEAN or NUMERIC (1–5) — Incident resolution quality
    - Custom evaluation scores: CATEGORICAL, NUMERIC, etc.

    Returns:
        Structured score record dictionary confirming persistence in local registry and Langfuse.
    """
    session_data = ensure_session_trace(event_id)

    # Determine Langfuse score data type
    data_type: ScoreDataType = "NUMERIC"
    normalized_value: float | str | bool = value

    if name == "user_thumbs":
        data_type = "BOOLEAN"
        if isinstance(value, bool):
            normalized_value = value
        elif isinstance(value, (int, float)):
            normalized_value = bool(value > 0)
        else:
            normalized_value = str(value).lower() in ("true", "1", "yes")
    elif name in ("user_rating", "overall_outcome"):
        data_type = "NUMERIC"
        try:
            normalized_value = float(value)
        except (ValueError, TypeError):
            normalized_value = 1.0
    elif isinstance(value, bool):
        data_type = "BOOLEAN"
    elif isinstance(value, (int, float)):
        data_type = "NUMERIC"
        normalized_value = float(value)
    else:
        data_type = "TEXT"
        normalized_value = str(value)

    score_record: dict[str, Any] = {
        "score_name": name,
        "data_type": data_type,
        "value": normalized_value,
        "comment": comment,
        "event_id": event_id,
        "span_id": span_id,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Dispatch to live Langfuse client if configured
    langfuse_client = get_langfuse_client()
    if langfuse_client:
        try:
            # If value is boolean, Langfuse create_score accepts 1.0/0.0 or bool
            langfuse_value = 1.0 if normalized_value is True else (0.0 if normalized_value is False else normalized_value)
            langfuse_client.create_score(
                name=name,
                value=langfuse_value,
                trace_id=event_id,
                observation_id=span_id,
                data_type=data_type,
                comment=comment,
                metadata=metadata,
            )
            score_record["langfuse_synced"] = True
        except Exception as exc:
            score_record["langfuse_synced"] = False
            score_record["langfuse_error"] = str(exc)
    else:
        score_record["langfuse_synced"] = False
        score_record["note"] = "Offline/mock telemetry mode active"

    session_data["scores"].append(score_record)
    return score_record
