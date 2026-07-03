"""Tests for backend construction from the model registry."""

from __future__ import annotations

import pytest

from masar.config import ModelSpec, RoutingConfig
from masar.llm.base import BackendError
from masar.llm.factory import build_backend, build_backends
from masar.llm.mock import MockBackend
from masar.llm.openai_compatible import OpenAICompatibleBackend


def test_build_mock_backend() -> None:
    spec = ModelSpec(name="m", backend="mock", model_id="mock-7")
    backend = build_backend(spec, env={})
    assert isinstance(backend, MockBackend)
    assert backend.model_id == "mock-7"


def test_build_openai_backend_reads_key_from_named_env() -> None:
    spec = ModelSpec(name="frontier", backend="openai", model_id="gpt-x", api_key_env="MY_KEY")
    backend = build_backend(spec, env={"MY_KEY": "sk-abc"})
    assert isinstance(backend, OpenAICompatibleBackend)
    assert backend.model_id == "gpt-x"


def test_build_openai_backend_missing_key_fails() -> None:
    spec = ModelSpec(name="frontier", backend="openai", model_id="gpt-x", api_key_env="MY_KEY")
    with pytest.raises(BackendError, match="MY_KEY"):
        build_backend(spec, env={})


def test_unknown_backend_is_rejected_defensively() -> None:
    # ModelSpec validation normally blocks unknown backends; construct one
    # unvalidated to prove the factory still guards against it.
    spec = ModelSpec.model_construct(name="x", backend="bogus", model_id="y")
    with pytest.raises(BackendError, match="unknown backend"):
        build_backend(spec, env={})


def test_build_backends_maps_names() -> None:
    config = RoutingConfig.model_validate(
        {
            "label": "heuristic v0 — pending mizan M2 data",
            "models": [
                {"name": "a", "backend": "mock", "model_id": "mock-a", "sovereign": True},
                {"name": "b", "backend": "mock", "model_id": "mock-b"},
            ],
            "routes": [{"name": "default", "primary": "b"}],
        }
    )
    backends = build_backends(config, env={})
    assert set(backends) == {"a", "b"}
    assert backends["a"].model_id == "mock-a"
