"""Tests for the policy engine's route resolution and precedence."""

from __future__ import annotations

import pytest

from masar.config import RoutingConfig
from masar.domain import Classification, LanguageClass, SensitivityClass, TaskType
from masar.policy.engine import PolicyEngine, PolicyError, ResolvedRoute


def _engine() -> PolicyEngine:
    config = RoutingConfig.model_validate(
        {
            "label": "heuristic v0 - pending mizan M2 data",
            "defaults": {"timeout_seconds": 30.0, "retries": 1},
            "models": [
                {"name": "mock-sovereign", "model_id": "mock-sov", "sovereign": True},
                {"name": "mock-frontier", "model_id": "mock-fr"},
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
                    "timeout_seconds": 20.0,
                },
                {
                    "name": "default",
                    "match": {"sensitivity": "*"},
                    "primary": "mock-frontier",
                    "fallbacks": ["mock-sovereign"],
                },
            ],
        }
    )
    return PolicyEngine(config)


def _classify(
    sensitivity: SensitivityClass,
    language: LanguageClass,
    task: TaskType = TaskType.CHAT,
) -> Classification:
    return Classification(sensitivity=sensitivity, language=language, task=task)


def test_sovereign_request_takes_sovereign_route() -> None:
    resolved = _engine().resolve(_classify(SensitivityClass.SOVEREIGN, LanguageClass.EN))
    assert resolved.route_name == "sovereign-any"
    assert resolved.sovereign is True
    assert resolved.chain == ["mock-sovereign"]


def test_sovereign_arabic_still_takes_first_matching_route() -> None:
    # sovereign-any is listed before arabic-standard, so it wins on precedence.
    resolved = _engine().resolve(_classify(SensitivityClass.SOVEREIGN, LanguageClass.AR))
    assert resolved.route_name == "sovereign-any"


def test_standard_arabic_takes_arabic_route_with_override() -> None:
    resolved = _engine().resolve(_classify(SensitivityClass.STANDARD, LanguageClass.AR))
    assert resolved.route_name == "arabic-standard"
    assert resolved.chain == ["mock-frontier", "mock-sovereign"]
    assert resolved.timeout_seconds == 20.0
    assert resolved.retries == 1


def test_standard_english_falls_through_to_default() -> None:
    resolved = _engine().resolve(_classify(SensitivityClass.STANDARD, LanguageClass.EN))
    assert resolved.route_name == "default"
    assert resolved.timeout_seconds == 30.0


def test_unknown_language_standard_takes_default() -> None:
    resolved = _engine().resolve(_classify(SensitivityClass.STANDARD, LanguageClass.UNKNOWN))
    assert resolved.route_name == "default"


def test_resolve_raises_without_catch_all() -> None:
    # A validated config always has a catch-all; bypass validation with
    # model_construct to hand the engine a table with only a narrow route.
    from masar.config import ModelSpec, Route, RouteMatch, RoutingDefaults

    config = RoutingConfig.model_construct(
        version=0,
        label="x",
        models=[ModelSpec(name="m", model_id="mock")],
        routes=[Route(name="ar-only", match=RouteMatch(language="ar"), primary="m")],
        defaults=RoutingDefaults(),
        cost_source="",
    )
    with pytest.raises(PolicyError):
        PolicyEngine(config).resolve(_classify(SensitivityClass.STANDARD, LanguageClass.EN))


def test_resolved_route_requires_nonempty_chain() -> None:
    with pytest.raises(ValueError):
        ResolvedRoute(route_name="r", sovereign=False, chain=[], timeout_seconds=1.0, retries=0)
