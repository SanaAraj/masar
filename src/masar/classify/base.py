"""The classifier interface.

A classifier turns a :class:`ClassifierInput` into a :class:`Classification`.
The interface is a ``Protocol`` so the rule-based v0 classifier can later be
swapped for an ML one without touching the policy engine or the API layer.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from masar.domain import Classification


class ClassifierInput(BaseModel):
    """The signal a classifier sees for one request.

    ``text`` is the concatenation of the message contents (system and user), so
    sensitivity and language detectors see the whole prompt. ``has_tools`` is
    True when the request supplied tool schemas, the strongest tool-use signal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    has_tools: bool = Field(default=False)


class Classifier(Protocol):
    """Anything that can classify a request."""

    def classify(self, request: ClassifierInput) -> Classification:
        """Return the classification for ``request``."""
        ...
