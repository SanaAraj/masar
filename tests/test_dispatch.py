"""Tests for the dispatcher: retries, fallback, timeout, and latency."""

from __future__ import annotations

import pytest

from masar.dispatch import Dispatcher, DispatchError
from masar.llm.base import Backend, BackendError, BackendTimeout, ChatParams, ChatResult, Message
from masar.llm.mock import MockBackend
from masar.policy.engine import ResolvedRoute


class _FakeClock:
    """A monotonic clock advancing by a fixed step per call."""

    def __init__(self, step: float = 0.25) -> None:
        self._t = 0.0
        self._step = step

    def __call__(self) -> float:
        value = self._t
        self._t += self._step
        return value


class _FailingBackend(Backend):
    """Fails the first ``fail_times`` calls (or always if ``fail_times`` is None)."""

    def __init__(self, model_id: str, exc: BackendError, fail_times: int | None = None) -> None:
        self._model_id = model_id
        self._exc = exc
        self._fail_times = fail_times
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(self, messages, params, timeout=None) -> ChatResult:
        self.calls += 1
        if self._fail_times is None or self.calls <= self._fail_times:
            raise self._exc
        return ChatResult(
            text="recovered", model_id=self._model_id, prompt_tokens=1, completion_tokens=1
        )


class _RecordingBackend(MockBackend):
    """A mock that remembers the timeout it was called with."""

    def __init__(self, model_id: str) -> None:
        super().__init__(model_id)
        self.seen_timeouts: list[float | None] = []

    def chat(self, messages, params, timeout=None) -> ChatResult:
        self.seen_timeouts.append(timeout)
        return super().chat(messages, params, timeout)


def _route(chain: list[str], *, retries: int = 0, timeout: float = 30.0) -> ResolvedRoute:
    return ResolvedRoute(
        route_name="r", sovereign=False, chain=chain, timeout_seconds=timeout, retries=retries
    )


_MESSAGES = [Message(role="user", content="hello")]


def test_success_on_primary() -> None:
    dispatcher = Dispatcher({"a": MockBackend("a")}, clock=_FakeClock())
    outcome = dispatcher.dispatch(_route(["a"]), _MESSAGES, ChatParams())
    assert outcome.model_name == "a"
    assert outcome.fallback_used is False
    assert len(outcome.attempts) == 1
    assert outcome.attempts[0].ok is True
    assert outcome.latency_ms == 250.0


def test_falls_back_to_next_model_on_error() -> None:
    backends = {
        "a": _FailingBackend("a", BackendError("boom")),
        "b": MockBackend("b"),
    }
    outcome = Dispatcher(backends, clock=_FakeClock()).dispatch(
        _route(["a", "b"]), _MESSAGES, ChatParams()
    )
    assert outcome.model_name == "b"
    assert outcome.fallback_used is True
    assert [a.ok for a in outcome.attempts] == [False, True]


def test_retries_before_falling_through() -> None:
    flaky = _FailingBackend("a", BackendError("transient"), fail_times=2)
    backends = {"a": flaky}
    outcome = Dispatcher(backends, clock=_FakeClock()).dispatch(
        _route(["a"], retries=2), _MESSAGES, ChatParams()
    )
    assert flaky.calls == 3  # two failures then success
    assert outcome.model_name == "a"
    assert [a.ok for a in outcome.attempts] == [False, False, True]


def test_timeout_is_treated_as_failure_and_falls_back() -> None:
    backends = {
        "a": _FailingBackend("a", BackendTimeout("a: timed out after 5s")),
        "b": MockBackend("b"),
    }
    outcome = Dispatcher(backends, clock=_FakeClock()).dispatch(
        _route(["a", "b"], timeout=5.0), _MESSAGES, ChatParams()
    )
    assert outcome.model_name == "b"
    assert "timed out" in outcome.attempts[0].error


def test_route_timeout_is_passed_to_backend() -> None:
    recording = _RecordingBackend("a")
    Dispatcher({"a": recording}, clock=_FakeClock()).dispatch(
        _route(["a"], timeout=12.5), _MESSAGES, ChatParams()
    )
    assert recording.seen_timeouts == [12.5]


def test_all_models_failing_raises_dispatch_error() -> None:
    backends = {
        "a": _FailingBackend("a", BackendError("no")),
        "b": _FailingBackend("b", BackendError("nope")),
    }
    with pytest.raises(DispatchError) as excinfo:
        Dispatcher(backends, clock=_FakeClock()).dispatch(
            _route(["a", "b"], retries=1), _MESSAGES, ChatParams()
        )
    # two models x (1 retry + 1) attempts = 4 failures recorded.
    assert len(excinfo.value.attempts) == 4
    assert excinfo.value.latency_ms == 250.0


def test_missing_backend_is_recorded_and_skipped() -> None:
    backends = {"b": MockBackend("b")}
    outcome = Dispatcher(backends, clock=_FakeClock()).dispatch(
        _route(["missing", "b"]), _MESSAGES, ChatParams()
    )
    assert outcome.model_name == "b"
    assert outcome.attempts[0].ok is False
    assert "no backend registered" in outcome.attempts[0].error
