"""Tests for language classification and the soft Gulf-dialect signal."""

from __future__ import annotations

from masar.classify.language import classify_language
from masar.domain import Dialect, LanguageClass


def test_english_text() -> None:
    language, dialect, signals = classify_language("What is the capital of Saudi Arabia?")
    assert language is LanguageClass.EN
    assert dialect is None
    assert "lang:latin-script" in signals


def test_msa_text_defaults_to_msa_signal() -> None:
    language, dialect, signals = classify_language("ما هي عاصمة المملكة العربية السعودية؟")
    assert language is LanguageClass.AR
    assert dialect is Dialect.MSA
    assert "dialect:msa-default" in signals


def test_gulf_markers_detected() -> None:
    language, dialect, signals = classify_language("وش رايك نروح مطعم زين؟")
    assert language is LanguageClass.AR
    assert dialect is Dialect.GULF
    assert "dialect:gulf-marker:وش" in signals
    assert "dialect:gulf-marker:زين" in signals


def test_mixed_script_is_arabic() -> None:
    language, dialect, _ = classify_language("Please translate: وش الأخبار")
    assert language is LanguageClass.AR
    assert dialect is Dialect.GULF


def test_msa_word_containing_marker_substring_stays_msa() -> None:
    # "الزينة" contains the marker "زين" as a substring but not as a whole word.
    language, dialect, _ = classify_language("هذه الزينة جميلة جدا")
    assert language is LanguageClass.AR
    assert dialect is Dialect.MSA


def test_digits_only_is_unknown() -> None:
    language, dialect, signals = classify_language("12345 67890")
    assert language is LanguageClass.UNKNOWN
    assert dialect is None
    assert "lang:no-letters" in signals


def test_empty_is_unknown() -> None:
    language, _, _ = classify_language("")
    assert language is LanguageClass.UNKNOWN
