"""The FastAPI application factory.

``create_app`` loads and validates the routing table, builds the model backends
(reading keys from the environment), and wires the classifier, policy engine,
dispatcher, and stats store onto the app state. A misconfigured table or a
missing key therefore fails loudly at startup, not mid-request.

Run it with uvicorn's factory mode, which calls this function with no arguments::

    uvicorn masar.app:create_app --factory

The routing table is chosen by the ``MASAR_CONFIG`` environment variable,
defaulting to the committed heuristic v0 table.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from fastapi import FastAPI

from masar.accounting import StatsStore
from masar.api.routes import router
from masar.classify.rules import RuleBasedClassifier
from masar.config import load_config
from masar.dispatch import Dispatcher
from masar.llm.factory import build_backends
from masar.policy.engine import PolicyEngine

DEFAULT_CONFIG_PATH = "configs/routing.v0.yaml"


def create_app(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> FastAPI:
    """Build a configured masar application.

    Args:
        config_path: routing table to load; defaults to ``MASAR_CONFIG`` or the
            committed heuristic v0 table.
        env: environment mapping for resolving backend keys (defaults to
            ``os.environ``).
        clock: monotonic clock for dispatch latency (injectable for tests).

    Raises:
        ConfigError: if the routing table is missing or invalid.
        BackendError: if a model's backend cannot be constructed.
    """
    resolved_path = config_path or os.environ.get("MASAR_CONFIG", DEFAULT_CONFIG_PATH)
    config = load_config(resolved_path)
    backends = build_backends(config, env)

    app = FastAPI(
        title="masar",
        summary="Eval-driven, sovereignty-aware LLM router",
        version="0.1.0",
    )
    app.state.config = config
    app.state.classifier = RuleBasedClassifier()
    app.state.engine = PolicyEngine(config)
    app.state.dispatcher = Dispatcher(backends, clock=clock)
    app.state.stats = StatsStore()
    app.include_router(router)
    return app
