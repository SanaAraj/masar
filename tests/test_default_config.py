"""The shipped heuristic v0 routing table must load, validate, and boot."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from masar.app import create_app
from masar.config import load_config

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "routing.v0.yaml"


def test_default_config_loads_and_is_labelled_pending() -> None:
    config = load_config(_CONFIG_PATH)
    assert "pending mizan" in config.label.lower()
    # Every sovereign route references only sovereign-hosted models (also
    # enforced by validation; asserted here as documentation of the invariant).
    by_name = {m.name: m for m in config.models}
    for route in config.routes:
        if route.sovereign:
            assert all(by_name[name].sovereign for name in route.chain)


def test_default_config_boots_and_routes() -> None:
    client = TestClient(create_app(_CONFIG_PATH, env={}))
    assert client.get("/healthz").json() == {"status": "ok"}

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "بريدي sana@example.com"}]},
    )
    assert resp.status_code == 200
    # PII → sovereign route → a sovereign-hosted model serves it.
    assert resp.headers["X-Masar-Route"] == "sovereign-any"
    assert resp.headers["X-Masar-Model"] == "mock-sovereign"
