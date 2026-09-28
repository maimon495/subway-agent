"""Record what the agent was asked, what it did, and what it said.

Cloud Run logs only that a request happened: "POST /chat 200 OK". Every bad
answer is a successful HTTP response, so the failures that actually matter —
the agent picking the wrong tool, or declining something it could have
answered — leave no trace at all. When a real question went wrong on
2026-09-25 there was nothing to go back to.

Each turn is written to BigQuery: the question, which tools ran with what
arguments, what they returned, the final answer and how long it took. That
makes failures reproducible after the fact, and the questions that went wrong
become the obvious starting point for a regression suite.

Logging is best-effort by construction. Telemetry must never be the reason a
rider does not get an answer, so every failure here is swallowed.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "subway-agent-nyc")
BQ_DATASET = os.getenv("AGENT_BQ_DATASET", "agent")
BQ_TABLE = os.getenv("AGENT_BQ_TABLE", "turns")
ENABLED = os.getenv("AGENT_TELEMETRY", "1") not in ("0", "false", "False")

SCHEMA = [
    ("turn_at", "TIMESTAMP"),
    ("user_id", "STRING"),
    ("question", "STRING"),
    ("answer", "STRING"),
    ("tool_calls", "STRING"),      # JSON: [{name, args, result_preview}]
    ("tool_names", "STRING"),      # repeated, for cheap filtering
    ("used_any_tool", "BOOLEAN"),
    ("latency_ms", "INTEGER"),
    ("model", "STRING"),
    ("error", "STRING"),
]

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from google.cloud import bigquery

                client = bigquery.Client(project=GCP_PROJECT)
                dataset_ref = bigquery.DatasetReference(GCP_PROJECT, BQ_DATASET)
                try:
                    client.get_dataset(dataset_ref)
                except Exception:
                    dataset = bigquery.Dataset(dataset_ref)
                    dataset.location = "US"
                    client.create_dataset(dataset, exists_ok=True)
                table_ref = dataset_ref.table(BQ_TABLE)
                try:
                    client.get_table(table_ref)
                except Exception:
                    table = bigquery.Table(
                        table_ref,
                        schema=[bigquery.SchemaField(n, t) for n, t in SCHEMA],
                    )
                    table.time_partitioning = bigquery.TimePartitioning(field="turn_at")
                    client.create_table(table, exists_ok=True)
                _client = client
    return _client


def extract_tool_calls(messages: list) -> list[dict[str, Any]]:
    """Pull tool calls and their results out of a finished LangGraph run."""
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict] = {}
    for msg in messages or []:
        for call in getattr(msg, "tool_calls", None) or []:
            entry = {
                "name": call.get("name"),
                "args": call.get("args"),
                "result_preview": None,
            }
            calls.append(entry)
            if call.get("id"):
                by_id[call["id"]] = entry
        # ToolMessages carry the result, linked back by tool_call_id.
        call_id = getattr(msg, "tool_call_id", None)
        if call_id and call_id in by_id:
            content = getattr(msg, "content", "")
            by_id[call_id]["result_preview"] = str(content)[:600]
    return calls


def record_turn(
    question: str,
    answer: str,
    messages: Optional[list] = None,
    user_id: str = "default",
    latency_ms: Optional[int] = None,
    model: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Best effort: never let telemetry break the reply."""
    if not ENABLED:
        return
    try:
        calls = extract_tool_calls(messages or [])
        row = {
            "turn_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "question": (question or "")[:2000],
            "answer": (answer or "")[:4000],
            "tool_calls": json.dumps(calls, default=str)[:20000],
            "tool_names": ",".join(c["name"] or "?" for c in calls),
            "used_any_tool": bool(calls),
            "latency_ms": latency_ms,
            "model": model,
            "error": (error or None),
        }
        client = _get_client()
        table = client.get_table(f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}")
        errors = client.insert_rows_json(table, [row])
        if errors:
            log.warning("telemetry insert rejected: %s", errors[:2])
    except Exception as exc:
        log.warning("telemetry failed (ignored): %s", exc)
