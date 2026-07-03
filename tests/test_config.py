"""Tests for the routing table schema and its startup invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from masar.config import ConfigError, Route, RouteMatch, RoutingConfig, load_config


def _base_config() -> dict:
    """A minimal valid routing table as a plain dict, ready to be mutated."""
    return {
        "version": 0,
        "label": "heuristic v0 — pending mizan M2 data",
        "models": [
            {
                "name": "mock-sovereign",
                "backend": "mock",
                "model_id": "mock-sov-1",
                "sovereign": True,
            },
            {
                "name": "mock-frontier",
                "backend": "mock",
                "model_id": "mock-fr-1",
                "sovereign": False,
            },
        ],
        "routes": [
            {
                "name": "sovereign-any",
                "match": {"sensitivity": "sovereign"},
                "sovereign": True,
                "primary": "mock-sovereign",
            },
            {
                "name": "default",
                "match": {"sensitivity": "*", "language": "*", "task": "*"},
                "primary": "mock-frontier",
                "fallbacks": ["mock-sovereign"],
            },
        ],
    }


def _write(tmp_path: Path, config: dict) -> Path:
    import yaml

    path = tmp_path / "routing.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, _base_config()))
    assert config.label.startswith("heuristic v0")
    assert config.spec_for("mock-sovereign").sovereign is True
    assert [r.name for r in config.routes] == ["sovereign-any", "default"]


def test_sovereign_route_to_nonsovereign_model_fails(tmp_path: Path) -> None:
    config = _base_config()
    # Point the sovereign route's primary at the non-sovereign model.
    config["routes"][0]["primary"] = "mock-frontier"
    with pytest.raises(ConfigError, match="sovereign route"):
        load_config(_write(tmp_path, config))


def test_sovereign_route_with_nonsovereign_fallback_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"][0]["fallbacks"] = ["mock-frontier"]
    with pytest.raises(ConfigError, match="not sovereign"):
        load_config(_write(tmp_path, config))


def test_unknown_model_reference_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"][1]["fallbacks"] = ["does-not-exist"]
    with pytest.raises(ConfigError, match="unknown model 'does-not-exist'"):
        load_config(_write(tmp_path, config))


def test_missing_catch_all_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"][1]["match"] = {"language": "ar"}
    with pytest.raises(ConfigError, match="catch-all"):
        load_config(_write(tmp_path, config))


def test_route_after_catch_all_is_rejected_as_dead(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"].append(
        {"name": "dead", "match": {"language": "en"}, "primary": "mock-frontier"}
    )
    with pytest.raises(ConfigError, match="unreachable"):
        load_config(_write(tmp_path, config))


def test_duplicate_model_names_fail(tmp_path: Path) -> None:
    config = _base_config()
    config["models"][1]["name"] = "mock-sovereign"
    with pytest.raises(ConfigError, match="model names must be unique"):
        load_config(_write(tmp_path, config))


def test_duplicate_route_names_fail(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"][1]["name"] = "sovereign-any"
    with pytest.raises(ConfigError, match="route names must be unique"):
        load_config(_write(tmp_path, config))


def test_unknown_backend_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["models"][0]["backend"] = "anthropic"
    with pytest.raises(ConfigError, match="unknown backend"):
        load_config(_write(tmp_path, config))


def test_invalid_match_value_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["routes"][0]["match"] = {"language": "fr"}
    with pytest.raises(ConfigError, match="match.language"):
        load_config(_write(tmp_path, config))


def test_negative_cost_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["models"][0]["cost_per_1k_input_usd"] = -1.0
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, config))


def test_timeout_and_retries_resolution() -> None:
    config = RoutingConfig.model_validate(_base_config())
    default_route = config.routes[1]
    assert config.timeout_for(default_route) == 30.0
    assert config.retries_for(default_route) == 1

    overridden = Route(
        name="fast",
        match=RouteMatch(),
        primary="mock-frontier",
        timeout_seconds=5.0,
        retries=3,
    )
    assert config.timeout_for(overridden) == 5.0
    assert config.retries_for(overridden) == 3


def test_spec_for_unknown_raises() -> None:
    config = RoutingConfig.model_validate(_base_config())
    with pytest.raises(KeyError):
        config.spec_for("nope")


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.yaml")


def test_load_config_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(path)


def test_chain_orders_primary_first() -> None:
    route = Route(name="r", primary="a", fallbacks=["b", "c"])
    assert route.chain == ["a", "b", "c"]
