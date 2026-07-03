"""Tests for the OpenAI-compatible backend using a mocked httpx transport."""

from __future__ import annotations

import json

import httpx
import pytest

from masar.llm.base import BackendError, BackendTimeout, ChatParams, Message
from masar.llm.openai_compatible import OpenAICompatibleBackend


def _backend(handler, model_id: str = "gpt-x") -> OpenAICompatibleBackend:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleBackend(
        model_id, base_url="https://api.test/v1", api_key="sk-test", client=client
    )


def _msgs(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def test_sends_request_and_parses_content_and_usage() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        seen["timeout"] = request.extensions.get("timeout")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "الرياض"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 2},
            },
        )

    backend = _backend(handler)
    result = backend.chat(
        _msgs("ما هي عاصمة السعودية؟"), ChatParams(temperature=0.2, seed=7), timeout=9.0
    )

    assert result.text == "الرياض"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 2
    assert result.usage_estimated is False
    assert seen["url"] == "https://api.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "gpt-x"
    assert seen["body"]["messages"] == [{"role": "user", "content": "ما هي عاصمة السعودية؟"}]
    assert seen["body"]["seed"] == 7
    # The per-route timeout is applied at the HTTP layer.
    assert seen["timeout"]["read"] == 9.0


def test_usage_estimated_when_provider_omits_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "one two three"}}]})

    result = _backend(handler).chat(_msgs("hello there"), ChatParams())
    assert result.usage_estimated is True
    assert result.prompt_tokens == 2  # "hello there"
    assert result.completion_tokens == 3  # "one two three"


def test_seed_omitted_when_none() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _backend(handler).chat(_msgs("hi"), ChatParams(seed=None))
    assert "seed" not in seen["body"]


def test_non_200_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    with pytest.raises(BackendError, match="HTTP 429"):
        _backend(handler).chat(_msgs("hi"), ChatParams())


def test_timeout_raises_backend_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(BackendTimeout, match="timed out"):
        _backend(handler).chat(_msgs("hi"), ChatParams(), timeout=0.5)


def test_malformed_shape_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(BackendError, match="unexpected response shape"):
        _backend(handler).chat(_msgs("hi"), ChatParams())


def test_null_content_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    with pytest.raises(BackendError, match="no content"):
        _backend(handler).chat(_msgs("hi"), ChatParams())
