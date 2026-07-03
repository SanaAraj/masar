"""Backend abstraction and shared value objects for the chat layer.

Backends are intentionally thin: given a list of messages and decoding params
they return generated text plus token usage. Routing, retries, fallback, and
accounting live above this layer, so a backend only has to turn messages into a
:class:`ChatResult`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field


class BackendError(RuntimeError):
    """Raised when a model backend fails to return a usable response."""


class BackendTimeout(BackendError):
    """Raised when a backend call exceeds its allotted time.

    A distinct type so the dispatcher can record timeouts separately from other
    failures, though both trigger the same retry/fallback behaviour.
    """


def approx_token_count(text: str) -> int:
    """A deliberately simple, language-agnostic token estimate.

    Whitespace-delimited word count — not a real BPE tokenizer. It is used by the
    mock backend and as a fallback when a provider omits usage data; any cost
    derived from it is flagged as estimated so tables never imply false precision.
    """
    return len(text.split())


class Message(BaseModel):
    """One chat message handed to a backend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    content: str


class ChatParams(BaseModel):
    """Decoding parameters for a generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int = Field(default=512, gt=0)
    seed: int | None = None


class ChatResult(BaseModel):
    """A single generation annotated with its token usage and provenance.

    ``usage_estimated`` is True when token counts were approximated locally
    because the provider did not report them.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    model_id: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    usage_estimated: bool = False

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens


class Backend(ABC):
    """A chat-generation backend for one model."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier for the underlying model (recorded in results)."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        params: ChatParams,
        timeout: float | None = None,
    ) -> ChatResult:
        """Generate a completion for ``messages`` under ``params``.

        ``timeout`` bounds a single call in seconds (``None`` uses the backend
        default). Implementations raise :class:`BackendTimeout` when exceeded and
        :class:`BackendError` for any other failure.
        """
