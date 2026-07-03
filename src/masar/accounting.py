"""Cost and latency accounting with an in-memory stats store.

``estimate_cost`` turns token usage into a USD figure from a model's configured
per-1k prices. :class:`StatsStore` aggregates per-request accounting keyed by
``(route, model)`` behind a lock, since sync FastAPI handlers run in a thread
pool. Persistence is out of scope for M1 (stats reset on restart) — see the
roadmap.

Cost is only as trustworthy as the prices in the config. The mock backend is
priced at ``0.0``, so its cost is truthfully zero; real prices must be sourced
and dated before a real model is activated (see ``RoutingConfig.cost_source``).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from masar.config import ModelSpec

_FAILED_MODEL = "(failed)"


def estimate_cost(spec: ModelSpec, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate the USD cost of a generation from the model's per-1k prices."""
    return (
        prompt_tokens / 1000.0 * spec.cost_per_1k_input_usd
        + completion_tokens / 1000.0 * spec.cost_per_1k_output_usd
    )


@dataclass
class _Accumulator:
    """Mutable running totals for one (route, model) key."""

    requests: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms_sum: float = 0.0
    latency_ms_min: float | None = field(default=None)
    latency_ms_max: float | None = field(default=None)


class RouteModelStat(BaseModel):
    """Aggregated accounting for one route/model pair."""

    model_config = ConfigDict(extra="forbid")

    route: str
    model: str
    requests: int
    errors: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float


class StatsTotals(BaseModel):
    """Roll-up across every route/model pair."""

    model_config = ConfigDict(extra="forbid")

    requests: int
    errors: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class StatsSnapshot(BaseModel):
    """A point-in-time view of the stats store for the ``/stats`` endpoint."""

    model_config = ConfigDict(extra="forbid")

    totals: StatsTotals
    by_route_model: list[RouteModelStat]


class StatsStore:
    """Thread-safe in-memory aggregation of per-request accounting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[tuple[str, str], _Accumulator] = {}

    def record(
        self,
        *,
        route: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: float,
        ok: bool,
    ) -> None:
        """Fold one request's accounting into the running totals."""
        with self._lock:
            acc = self._by_key.setdefault((route, model), _Accumulator())
            acc.requests += 1
            if not ok:
                acc.errors += 1
            acc.prompt_tokens += prompt_tokens
            acc.completion_tokens += completion_tokens
            acc.cost_usd += cost_usd
            acc.latency_ms_sum += latency_ms
            acc.latency_ms_min = (
                latency_ms if acc.latency_ms_min is None else min(acc.latency_ms_min, latency_ms)
            )
            acc.latency_ms_max = (
                latency_ms if acc.latency_ms_max is None else max(acc.latency_ms_max, latency_ms)
            )

    def record_failure(self, *, route: str, latency_ms: float) -> None:
        """Record a request that no model could serve."""
        self.record(
            route=route,
            model=_FAILED_MODEL,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=latency_ms,
            ok=False,
        )

    def snapshot(self) -> StatsSnapshot:
        """Return current aggregates, ordered by route then model."""
        with self._lock:
            entries: list[RouteModelStat] = []
            totals = _Accumulator()
            for (route, model), acc in sorted(self._by_key.items()):
                entries.append(
                    RouteModelStat(
                        route=route,
                        model=model,
                        requests=acc.requests,
                        errors=acc.errors,
                        prompt_tokens=acc.prompt_tokens,
                        completion_tokens=acc.completion_tokens,
                        cost_usd=round(acc.cost_usd, 6),
                        avg_latency_ms=round(acc.latency_ms_sum / acc.requests, 3),
                        min_latency_ms=round(acc.latency_ms_min or 0.0, 3),
                        max_latency_ms=round(acc.latency_ms_max or 0.0, 3),
                    )
                )
                totals.requests += acc.requests
                totals.errors += acc.errors
                totals.prompt_tokens += acc.prompt_tokens
                totals.completion_tokens += acc.completion_tokens
                totals.cost_usd += acc.cost_usd

            return StatsSnapshot(
                totals=StatsTotals(
                    requests=totals.requests,
                    errors=totals.errors,
                    prompt_tokens=totals.prompt_tokens,
                    completion_tokens=totals.completion_tokens,
                    cost_usd=round(totals.cost_usd, 6),
                ),
                by_route_model=entries,
            )
