"""Tests for task-type classification."""

from __future__ import annotations

from masar.classify.task import classify_task
from masar.domain import TaskType


def test_tools_present_is_tool_use() -> None:
    task, signals = classify_task("book a flight to Riyadh", has_tools=True)
    assert task is TaskType.TOOL_USE
    assert "task:tools-present" in signals


def test_tools_present_overrides_extract_phrasing() -> None:
    task, signals = classify_task("extract the JSON fields", has_tools=True)
    assert task is TaskType.TOOL_USE
    assert "task:tools-present" in signals


def test_tool_phrase_is_tool_use() -> None:
    task, signals = classify_task("call the tool to fetch the weather", has_tools=False)
    assert task is TaskType.TOOL_USE
    assert "task:tool-phrase" in signals


def test_english_extraction() -> None:
    task, signals = classify_task("extract the invoice fields as JSON", has_tools=False)
    assert task is TaskType.EXTRACTION
    assert "task:extract-phrase" in signals


def test_arabic_extraction() -> None:
    task, signals = classify_task("استخرج البيانات من هذا النص", has_tools=False)
    assert task is TaskType.EXTRACTION
    assert "task:extract-phrase" in signals


def test_plain_chat_is_default() -> None:
    task, signals = classify_task("كيف حالك اليوم؟", has_tools=False)
    assert task is TaskType.CHAT
    assert "task:default-chat" in signals
