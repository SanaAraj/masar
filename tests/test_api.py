"""End-to-end tests for the gateway via FastAPI's TestClient and the mock backend."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from masar.app import create_app
from masar.dispatch import Dispatcher
from masar.llm.base import Backend, BackendError, ChatResult


class _FixedClock:
    """Monotonic clock advancing 0.25s per call (250ms per dispatch)."""

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        value = self._t
        self._t += 0.25
        return value


class _AlwaysFail(Backend):
    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(self, messages, params, timeout=None) -> ChatResult:
        raise BackendError(f"{self._model_id} is down")


_CONFIG = {
    "version": 0,
    "label": "heuristic v0 - pending mizan M2 data",
    "cost_source": "mock models only (cost 0)",
    "models": [
        {"name": "mock-sovereign", "backend": "mock", "model_id": "mock-sov-1", "sovereign": True},
        {"name": "mock-frontier", "backend": "mock", "model_id": "mock-fr-1", "sovereign": False},
    ],
    "routes": [
        {
            "name": "sovereign-any",
            "match": {"sensitivity": "sovereign"},
            "sovereign": True,
            "primary": "mock-sovereign",
        },
        {
            "name": "arabic-standard",
            "match": {"sensitivity": "standard", "language": "ar"},
            "primary": "mock-frontier",
            "fallbacks": ["mock-sovereign"],
        },
        {
            "name": "default",
            "match": {"sensitivity": "*"},
            "primary": "mock-frontier",
            "fallbacks": ["mock-sovereign"],
        },
    ],
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    path = tmp_path / "routing.yaml"
    path.write_text(yaml.safe_dump(_CONFIG), encoding="utf-8")
    app = create_app(path, env={}, clock=_FixedClock())
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_english_chat_takes_default_route(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-anything",
            "messages": [{"role": "user", "content": "What is the capital of Qatar?"}],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Masar-Route"] == "default"
    assert resp.headers["X-Masar-Model"] == "mock-frontier"
    assert resp.headers["X-Masar-Classification"] == "standard/en/chat"
    assert resp.headers["X-Masar-Latency-Ms"] == "250.000"
    assert resp.headers["X-Masar-Fallback-Used"] == "false"

    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "mock-fr-1"
    assert body["choices"][0]["message"]["content"].startswith("[mock:mock-fr-1]")
    assert body["usage"]["total_tokens"] == (
        body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    )


def test_arabic_pii_takes_sovereign_route(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "راسلني على sana@example.com من فضلك"}]},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Masar-Route"] == "sovereign-any"
    assert resp.headers["X-Masar-Model"] == "mock-sovereign"
    assert resp.headers["X-Masar-Classification"].startswith("sovereign/ar/")


def test_tools_present_routes_as_tool_use(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "book a flight"}],
            "tools": [{"type": "function", "function": {"name": "book"}}],
        },
    )
    assert resp.headers["X-Masar-Classification"] == "standard/en/tool_use"


def test_stream_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert resp.status_code == 400


def test_empty_messages_is_unprocessable(client: TestClient) -> None:
    resp = client.post("/v1/chat/completions", json={"messages": []})
    assert resp.status_code == 422


def test_stats_reflect_traffic(client: TestClient) -> None:
    client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hello"}]})
    client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]})
    stats = client.get("/stats").json()
    assert stats["routing_label"] == "heuristic v0 - pending mizan M2 data"
    assert stats["cost_source"] == "mock models only (cost 0)"
    assert stats["totals"]["requests"] == 2
    assert stats["totals"]["cost_usd"] == 0.0
    entry = stats["by_route_model"][0]
    assert entry["route"] == "default"
    assert entry["model"] == "mock-frontier"


def test_dispatch_failure_returns_502_and_records_error(client: TestClient) -> None:
    client.app.state.dispatcher = Dispatcher(
        {
            "mock-frontier": _AlwaysFail("mock-frontier"),
            "mock-sovereign": _AlwaysFail("mock-sovereign"),
        },
        clock=_FixedClock(),
    )
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "upstream_error"
    assert resp.headers["X-Masar-Route"] == "default"

    stats = client.get("/stats").json()
    assert stats["totals"]["errors"] == 1
    assert any(e["model"] == "(failed)" for e in stats["by_route_model"])
