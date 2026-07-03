"""Chat backends for masar: a mock and any OpenAI-compatible endpoint.

The layer mirrors the mizan-evals backend pattern: a thin :class:`Backend`
abstraction, a deterministic :class:`MockBackend` for offline use, an
:class:`OpenAICompatibleBackend`, and a factory that reads credentials from the
environment by name.
"""

from __future__ import annotations

from masar.llm.base import (
    Backend,
    BackendError,
    BackendTimeout,
    ChatParams,
    ChatResult,
    Message,
    approx_token_count,
)
from masar.llm.factory import build_backend, build_backends
from masar.llm.mock import MockBackend
from masar.llm.openai_compatible import OpenAICompatibleBackend

__all__ = [
    "Backend",
    "BackendError",
    "BackendTimeout",
    "ChatParams",
    "ChatResult",
    "Message",
    "MockBackend",
    "OpenAICompatibleBackend",
    "approx_token_count",
    "build_backend",
    "build_backends",
]
