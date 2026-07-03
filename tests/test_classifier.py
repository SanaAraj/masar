"""Tests for the composed rule-based classifier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from masar.classify.base import ClassifierInput
from masar.classify.rules import RuleBasedClassifier
from masar.domain import Classification, LanguageClass, SensitivityClass, TaskType


def test_composes_all_three_dimensions() -> None:
    classifier = RuleBasedClassifier()
    request = ClassifierInput(
        text="هذا المستند سري، استخرج البيانات، بريدي sana@example.com",
        has_tools=False,
    )
    result = classifier.classify(request)

    assert result.sensitivity is SensitivityClass.SOVEREIGN
    assert result.language is LanguageClass.AR
    assert result.task is TaskType.EXTRACTION
    assert "pii:email" in result.signals
    assert "confidential:keyword-ar" in result.signals
    assert "lang:arabic-script" in result.signals
    assert "task:extract-phrase" in result.signals


def test_plain_english_chat() -> None:
    result = RuleBasedClassifier().classify(ClassifierInput(text="What is the capital of Qatar?"))
    assert result.sensitivity is SensitivityClass.STANDARD
    assert result.language is LanguageClass.EN
    assert result.task is TaskType.CHAT


def test_classification_is_frozen_and_hashable() -> None:
    result = RuleBasedClassifier().classify(ClassifierInput(text="hello"))
    with pytest.raises(ValidationError):
        result.sensitivity = SensitivityClass.SOVEREIGN  # type: ignore[misc]
    # Hashable, so it can key stats/aggregates.
    assert isinstance(hash(result), int)
    assert result in {result}


def test_classification_can_be_rebuilt_from_fields() -> None:
    result = RuleBasedClassifier().classify(ClassifierInput(text="hello"))
    clone = Classification(
        sensitivity=result.sensitivity,
        language=result.language,
        task=result.task,
        dialect=result.dialect,
        signals=result.signals,
    )
    assert clone == result
