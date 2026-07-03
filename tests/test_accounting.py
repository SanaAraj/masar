"""Tests for cost estimation and the in-memory stats store."""

from __future__ import annotations

import threading

from masar.accounting import StatsStore, estimate_cost
from masar.config import ModelSpec


def test_estimate_cost_uses_per_1k_prices() -> None:
    spec = ModelSpec(
        name="frontier",
        model_id="gpt-x",
        cost_per_1k_input_usd=3.0,
        cost_per_1k_output_usd=6.0,
    )
    # 2000 input tokens * $3/1k + 500 output tokens * $6/1k = 6.0 + 3.0
    assert estimate_cost(spec, 2000, 500) == 9.0


def test_mock_model_costs_zero() -> None:
    spec = ModelSpec(name="mock", model_id="mock-1")
    assert estimate_cost(spec, 1234, 5678) == 0.0


def test_stats_aggregate_by_route_and_model() -> None:
    store = StatsStore()
    store.record(
        route="default",
        model="mock-frontier",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.02,
        latency_ms=100.0,
        ok=True,
    )
    store.record(
        route="default",
        model="mock-frontier",
        prompt_tokens=20,
        completion_tokens=10,
        cost_usd=0.04,
        latency_ms=200.0,
        ok=True,
    )
    snapshot = store.snapshot()

    assert snapshot.totals.requests == 2
    assert snapshot.totals.prompt_tokens == 30
    assert snapshot.totals.completion_tokens == 15
    assert snapshot.totals.cost_usd == 0.06

    entry = snapshot.by_route_model[0]
    assert entry.route == "default"
    assert entry.model == "mock-frontier"
    assert entry.avg_latency_ms == 150.0
    assert entry.min_latency_ms == 100.0
    assert entry.max_latency_ms == 200.0


def test_separate_keys_are_not_merged() -> None:
    store = StatsStore()
    store.record(
        route="a",
        model="m1",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=10.0,
        ok=True,
    )
    store.record(
        route="b",
        model="m2",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=10.0,
        ok=True,
    )
    snapshot = store.snapshot()
    assert len(snapshot.by_route_model) == 2
    # sorted by (route, model)
    assert [(e.route, e.model) for e in snapshot.by_route_model] == [("a", "m1"), ("b", "m2")]


def test_record_failure_counts_as_error() -> None:
    store = StatsStore()
    store.record_failure(route="default", latency_ms=50.0)
    snapshot = store.snapshot()
    assert snapshot.totals.requests == 1
    assert snapshot.totals.errors == 1
    entry = snapshot.by_route_model[0]
    assert entry.model == "(failed)"
    assert entry.errors == 1


def test_empty_snapshot_has_zero_totals() -> None:
    snapshot = StatsStore().snapshot()
    assert snapshot.totals.requests == 0
    assert snapshot.by_route_model == []


def test_stats_store_is_thread_safe() -> None:
    store = StatsStore()

    def worker() -> None:
        for _ in range(1000):
            store.record(
                route="r",
                model="m",
                prompt_tokens=1,
                completion_tokens=1,
                cost_usd=0.001,
                latency_ms=1.0,
                ok=True,
            )

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = store.snapshot()
    assert snapshot.totals.requests == 8000
    assert snapshot.totals.prompt_tokens == 8000
