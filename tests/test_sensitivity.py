"""Tests for the sensitivity detector: PII, credentials, and confidential text."""

from __future__ import annotations

import pytest

from masar.classify.sensitivity import classify_sensitivity
from masar.domain import SensitivityClass


@pytest.mark.parametrize(
    ("text", "signal"),
    [
        ("contact me at sana@example.com", "pii:email"),
        ("my number is 0551234567", "pii:phone"),
        ("call +966512345678 please", "pii:phone"),
        ("card 4242 4242 4242 4242 on file", "pii:card"),
        ("iban SA0380000000608010167519", "pii:iban"),
        ("iqama 2345678901 attached", "pii:national-id"),
        ("key sk-ABCDEFGHIJKLMNOP1234", "credential:api-key"),
        ("aws AKIAIOSFODNN7EXAMPLE here", "credential:aws-key"),
        ("token eyJhbGciOi.JWTPAYLOAD01.sIgNaTuRe", "credential:jwt"),
        ("password: hunter2", "credential:secret-assignment"),
        ("هذا المستند سري للغاية", "confidential:keyword-ar"),
        ("This memo is confidential", "confidential:keyword-en"),
    ],
)
def test_sensitive_inputs_route_sovereign(text: str, signal: str) -> None:
    sensitivity, signals = classify_sensitivity(text)
    assert sensitivity is SensitivityClass.SOVEREIGN
    assert signal in signals


def test_private_key_header_detected() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIB..."
    sensitivity, signals = classify_sensitivity(text)
    assert sensitivity is SensitivityClass.SOVEREIGN
    assert "credential:private-key" in signals


@pytest.mark.parametrize(
    "text",
    [
        "What is the capital of Qatar?",
        "ما هي عاصمة قطر؟",
        "Summarise this article about renewable energy.",
        "رقم الطلب 12345",  # short digit run, not a national id / card
    ],
)
def test_benign_inputs_route_standard(text: str) -> None:
    sensitivity, signals = classify_sensitivity(text)
    assert sensitivity is SensitivityClass.STANDARD
    assert signals == []


def test_invalid_card_number_is_not_flagged() -> None:
    # 16 digits that fail the Luhn checksum must not be treated as a card.
    sensitivity, signals = classify_sensitivity("order ref 4242 4242 4242 4241")
    assert sensitivity is SensitivityClass.STANDARD
    assert signals == []


def test_multiple_signals_are_all_reported() -> None:
    _, signals = classify_sensitivity("email sana@example.com and password: hunter2")
    assert "pii:email" in signals
    assert "credential:secret-assignment" in signals
