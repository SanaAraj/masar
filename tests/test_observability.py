"""Tests for the structured decision record and its logging."""

from __future__ import annotations

import json
import logging

from masar.dispatch import Attempt
from masar.domain import Classification, Dialect, LanguageClass, SensitivityClass, TaskType
from masar.observability import decision_record, log_request


def _classification() -> Classification:
    return Classification(
        sensitivity=SensitivityClass.SOVEREIGN,
        language=LanguageClass.AR,
        task=TaskType.EXTRACTION,
        dialect=Dialect.GULF,
        signals=("pii:email", "lang:arabic-script"),
    )


def test_decision_record_captures_all_dimensions() -> None:
    record = decision_record(
        request_id="req-1",
        classification=_classification(),
        route_name="sovereign-any",
        served_model="mock-sovereign",
        attempts=[Attempt(model_name="mock-sovereign", model_id="mock-sov", ok=True)],
        prompt_tokens=12,
        completion_tokens=3,
        cost_usd=0.0,
        latency_ms=42.1234,
        ok=True,
    )
    assert record["request_id"] == "req-1"
    assert record["ok"] is True
    assert record["classification"]["sensitivity"] == "sovereign"
    assert record["classification"]["dialect"] == "gulf"
    assert record["classification"]["signals"] == ["pii:email", "lang:arabic-script"]
    assert record["route"] == "sovereign-any"
    assert record["served_model"] == "mock-sovereign"
    assert record["attempts"] == [{"model": "mock-sovereign", "ok": True, "error": None}]
    assert record["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}
    assert record["latency_ms"] == 42.123  # rounded to 3dp


def test_decision_record_handles_absent_dialect_and_failure() -> None:
    classification = Classification(
        sensitivity=SensitivityClass.STANDARD,
        language=LanguageClass.EN,
        task=TaskType.CHAT,
    )
    record = decision_record(
        request_id="req-2",
        classification=classification,
        route_name="default",
        served_model=None,
        attempts=[Attempt(model_name="m", model_id="m", ok=False, error="boom")],
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        latency_ms=5.0,
        ok=False,
    )
    assert record["classification"]["dialect"] is None
    assert record["served_model"] is None
    assert record["attempts"][0]["error"] == "boom"


def test_log_request_emits_valid_json_line(caplog) -> None:
    logger = logging.getLogger("masar.test.decision")
    record = decision_record(
        request_id="req-3",
        classification=_classification(),
        route_name="sovereign-any",
        served_model="mock-sovereign",
        attempts=[],
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=1.0,
        ok=True,
    )
    with caplog.at_level(logging.INFO, logger="masar.test.decision"):
        log_request(record, logger=logger)

    assert len(caplog.records) == 1
    parsed = json.loads(caplog.records[0].message)
    assert parsed["request_id"] == "req-3"
    # Arabic signals survive round-trip without ASCII escaping.
    assert parsed["classification"]["signals"] == ["pii:email", "lang:arabic-script"]
