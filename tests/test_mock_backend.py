"""Tests for the deterministic mock chat backend."""

from __future__ import annotations

from masar.llm.base import ChatParams, Message, approx_token_count
from masar.llm.mock import MockBackend


def _msgs(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def test_output_is_deterministic() -> None:
    backend = MockBackend("mock-a")
    first = backend.chat(_msgs("hello"), ChatParams())
    second = backend.chat(_msgs("hello"), ChatParams())
    assert first.text == second.text
    assert first.model_id == "mock-a"


def test_output_varies_by_model_and_prompt() -> None:
    a = MockBackend("mock-a").chat(_msgs("hello"), ChatParams()).text
    b = MockBackend("mock-b").chat(_msgs("hello"), ChatParams()).text
    c = MockBackend("mock-a").chat(_msgs("world"), ChatParams()).text
    assert a != b
    assert a != c


def test_scripted_override_returns_exact_text() -> None:
    backend = MockBackend("mock-a", scripted={"user: مرحبا": "أهلاً وسهلاً"})
    result = backend.chat(_msgs("مرحبا"), ChatParams())
    assert result.text == "أهلاً وسهلاً"


def test_token_counts_match_heuristic() -> None:
    backend = MockBackend("mock-a")
    messages = [
        Message(role="system", content="be brief"),
        Message(role="user", content="ما هي عاصمة قطر"),
    ]
    result = backend.chat(messages, ChatParams())
    assert result.prompt_tokens == sum(approx_token_count(m.content) for m in messages)
    assert result.completion_tokens == approx_token_count(result.text)
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens
    assert result.usage_estimated is False


def test_calls_counter_increments() -> None:
    backend = MockBackend("mock-a")
    assert backend.calls == 0
    backend.chat(_msgs("hi"), ChatParams())
    backend.chat(_msgs("hi"), ChatParams())
    assert backend.calls == 2
