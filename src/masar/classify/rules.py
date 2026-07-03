"""The heuristic v0 request classifier.

:class:`RuleBasedClassifier` composes the sensitivity, language, and task
detectors into one :class:`~masar.domain.Classification`, concatenating their
signals so a routing decision is fully explainable from the record. It is
stateless and cheap; the policy engine routes on its output.
"""

from __future__ import annotations

from masar.classify.base import ClassifierInput
from masar.classify.language import classify_language
from masar.classify.sensitivity import classify_sensitivity
from masar.classify.task import classify_task
from masar.domain import Classification


class RuleBasedClassifier:
    """Compose the rule-based detectors into a single classification."""

    def classify(self, request: ClassifierInput) -> Classification:
        """Classify ``request`` by sensitivity, language, and task type."""
        sensitivity, sensitivity_signals = classify_sensitivity(request.text)
        language, dialect, language_signals = classify_language(request.text)
        task, task_signals = classify_task(request.text, request.has_tools)
        return Classification(
            sensitivity=sensitivity,
            language=language,
            task=task,
            dialect=dialect,
            signals=tuple(sensitivity_signals + language_signals + task_signals),
        )
