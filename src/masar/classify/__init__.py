"""The pluggable, rule-based v0 request classifier.

Exposes the :class:`Classifier` protocol, its :class:`ClassifierInput`, and the
default :class:`RuleBasedClassifier` composing the sensitivity, language, and
task detectors.
"""

from __future__ import annotations

from masar.classify.base import Classifier, ClassifierInput
from masar.classify.language import classify_language
from masar.classify.rules import RuleBasedClassifier
from masar.classify.sensitivity import classify_sensitivity
from masar.classify.task import classify_task

__all__ = [
    "Classifier",
    "ClassifierInput",
    "RuleBasedClassifier",
    "classify_language",
    "classify_sensitivity",
    "classify_task",
]
