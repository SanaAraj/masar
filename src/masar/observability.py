"""Structured per-request decision logging.

``decision_record`` assembles a JSON-serialisable record explaining one routing
decision: the classification and the signals that drove it, the chosen route,
every backend attempt, and the resulting usage, cost, and latency. ``log_request``
emits it as a single JSON line. Keeping the record a plain dict makes it easy to
assert on in tests and to ship to any log sink.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from masar.dispatch import Attempt
from masar.domain import Classification

_LOGGER = logging.getLogger("masar.decision")


def decision_record(
    *,
    request_id: str,
    classification: Classification,
    route_name: str,
    served_model: str | None,
    attempts: list[Attempt],
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_ms: float,
    ok: bool,
) -> dict[str, Any]:
    """Build the structured record for one request's routing decision."""
    return {
        "request_id": request_id,
        "ok": ok,
        "classification": {
            "sensitivity": classification.sensitivity.value,
            "language": classification.language.value,
            "task": classification.task.value,
            "dialect": classification.dialect.value if classification.dialect else None,
            "signals": list(classification.signals),
        },
        "route": route_name,
        "served_model": served_model,
        "attempts": [{"model": a.model_name, "ok": a.ok, "error": a.error} for a in attempts],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "cost_usd": round(cost_usd, 6),
        "latency_ms": round(latency_ms, 3),
    }


def log_request(record: dict[str, Any], logger: logging.Logger | None = None) -> None:
    """Emit a decision record as a single JSON log line."""
    (logger or _LOGGER).info(json.dumps(record, ensure_ascii=False, sort_keys=True))
