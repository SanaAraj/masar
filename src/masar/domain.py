"""The classification vocabulary shared across the router.

A request is reduced to a small, explicit :class:`Classification`: its data
sensitivity, its language, and its task type, plus an optional soft dialect
signal and the list of raw signals that fired. The policy engine routes on
``(sensitivity, language, task)`` only; ``dialect`` is recorded for observability
but is deliberately **not** a routing dimension in this milestone, because
dialect-aware routing needs measured capability data (mizan-evals M2).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SensitivityClass(StrEnum):
    """Whether a request must be kept on sovereign-hosted infrastructure.

    ``SOVEREIGN`` is assigned when any PII, credential, or explicit-confidential
    signal fires; ``STANDARD`` otherwise. These are the only two routing classes;
    the specific signals that fired are preserved in :attr:`Classification.signals`.
    """

    STANDARD = "standard"
    SOVEREIGN = "sovereign"


class LanguageClass(StrEnum):
    """The dominant language of a request, for routing purposes.

    ``UNKNOWN`` covers input with no detectable Arabic script and no Latin
    letters (e.g. digits or symbols only); such requests fall through to the
    catch-all route rather than being silently assumed English.
    """

    EN = "en"
    AR = "ar"
    UNKNOWN = "unknown"


class TaskType(StrEnum):
    """The kind of work a request asks for.

    ``TOOL_USE`` is signalled by tool schemas on the request or explicit
    tool-calling phrasing; ``EXTRACTION`` by structured-output intent; ``CHAT``
    is the default.
    """

    CHAT = "chat"
    TOOL_USE = "tool_use"
    EXTRACTION = "extraction"


class Dialect(StrEnum):
    """A soft Arabic dialect signal (observability only in M1).

    ``MSA`` is Modern Standard Arabic; ``GULF`` is Gulf dialect. The signal is
    recorded on the classification and in the request log but does not influence
    routing until capability data exists to justify it.
    """

    MSA = "msa"
    GULF = "gulf"


class Classification(BaseModel):
    """The immutable outcome of classifying one request.

    ``signals`` holds human-readable tags for every rule that fired (e.g.
    ``"pii:email"``, ``"lang:arabic-script"``, ``"task:tools-present"``), so a
    routing decision can be explained after the fact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sensitivity: SensitivityClass
    language: LanguageClass
    task: TaskType
    dialect: Dialect | None = None
    signals: tuple[str, ...] = Field(default=())
