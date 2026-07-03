"""Rule-based task-type detection (heuristic v0).

Precedence, strongest signal first: tool schemas on the request, then explicit
tool-calling phrasing, then structured-extraction phrasing, then plain chat as
the default. Phrasing rules cover both English and Arabic.
"""

from __future__ import annotations

import re

from masar.domain import TaskType

_TOOL_PHRASE = re.compile(
    r"(?i)\b(?:call (?:the |a )?tool|use (?:the |a )?tool|function call|"
    r"invoke (?:the )?function|call (?:the )?api)\b"
    r"|استدعِ الأداة|استخدم الأداة|نفّذ دالة"
)
_EXTRACT_PHRASE = re.compile(
    r"(?i)\b(?:extract|parse|return (?:valid )?json|as json|"
    r"structured (?:data|output)|fill (?:in |out )?the schema)\b"
    r"|استخرج|حلّل النص|بصيغة json"
)


def classify_task(text: str, has_tools: bool) -> tuple[TaskType, list[str]]:
    """Classify the task type, returning the type and the signals that fired."""
    if has_tools:
        return TaskType.TOOL_USE, ["task:tools-present"]
    if _TOOL_PHRASE.search(text):
        return TaskType.TOOL_USE, ["task:tool-phrase"]
    if _EXTRACT_PHRASE.search(text):
        return TaskType.EXTRACTION, ["task:extract-phrase"]
    return TaskType.CHAT, ["task:default-chat"]
