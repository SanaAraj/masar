"""OpenAI-compatible request and response schemas for the gateway.

The request model is deliberately liberal (``extra="allow"``) so an existing
OpenAI client can point at masar unchanged and send fields masar does not act on
in M1. The ``model`` a client requests is recorded but not authoritative: the
policy engine decides which model actually serves the request.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """One inbound chat message (OpenAI shape)."""

    model_config = ConfigDict(extra="allow")

    role: str = Field(min_length=1)
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    """An OpenAI-compatible ``/v1/chat/completions`` request.

    ``tools`` presence is the strongest tool-use signal for the classifier;
    ``stream`` is rejected in M1 (a non-goal).
    """

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int | None = Field(default=None, gt=0)
    seed: int | None = None
    tools: list[dict] | None = None
    stream: bool = False


class ResponseMessage(BaseModel):
    """The assistant message in a completion choice."""

    model_config = ConfigDict(extra="forbid")

    role: str = "assistant"
    content: str


class Choice(BaseModel):
    """One completion choice (masar returns a single choice in M1)."""

    model_config = ConfigDict(extra="forbid")

    index: int = 0
    message: ResponseMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    """Token usage for a completion."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """An OpenAI-compatible chat completion response.

    ``model`` is the id of the model that actually served the request, which may
    differ from the one the client asked for because routing decides it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
