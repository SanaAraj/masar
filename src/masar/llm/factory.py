"""Construct backends from the model registry, reading keys from the environment.

Keys never live in the routing config: a :class:`~masar.config.ModelSpec` names
the environment variables to read (``api_key_env``, ``base_url_env``), and this
factory resolves them at construction time.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from masar.config import ModelSpec, RoutingConfig
from masar.llm.base import Backend, BackendError
from masar.llm.mock import MockBackend
from masar.llm.openai_compatible import OpenAICompatibleBackend

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def build_backend(spec: ModelSpec, env: Mapping[str, str] | None = None) -> Backend:
    """Build the backend named by ``spec.backend``.

    Args:
        spec: the model entry from the routing config.
        env: environment mapping to read keys from (defaults to ``os.environ``).

    Raises:
        BackendError: for an unknown backend or a missing required API key.
    """
    env = os.environ if env is None else env

    if spec.backend == "mock":
        return MockBackend(model_id=spec.model_id)

    if spec.backend == "openai":
        base_url = DEFAULT_OPENAI_BASE_URL
        if spec.base_url_env:
            base_url = env.get(spec.base_url_env) or base_url
        key_var = spec.api_key_env or "OPENAI_API_KEY"
        api_key = env.get(key_var)
        if not api_key:
            raise BackendError(
                f"model {spec.name!r}: OpenAI-compatible backend needs an API key; "
                f"set the {key_var} environment variable"
            )
        return OpenAICompatibleBackend(spec.model_id, base_url=base_url, api_key=api_key)

    raise BackendError(
        f"model {spec.name!r}: unknown backend {spec.backend!r} (expected 'mock' or 'openai')"
    )


def build_backends(
    config: RoutingConfig, env: Mapping[str, str] | None = None
) -> dict[str, Backend]:
    """Build every backend in the registry, keyed by logical model name.

    Raises:
        BackendError: if any model's backend cannot be constructed (e.g. a
            missing key), so a broken deployment fails at startup.
    """
    return {spec.name: build_backend(spec, env) for spec in config.models}
