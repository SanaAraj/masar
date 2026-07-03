"""Execute a resolved route against the model backends.

The dispatcher walks the model chain in order. Each model is tried up to
``retries + 1`` times; a :class:`~masar.llm.base.BackendError` (including a
timeout) drops through to the next attempt, then the next model. The first
success returns a :class:`DispatchOutcome`; exhausting the chain raises
:class:`DispatchError`. End-to-end latency is measured with an injectable clock
so it can be asserted deterministically in tests.

The per-route timeout is passed down to each backend call, so a slow provider is
bounded at the HTTP layer. Hard-killing a hung synchronous call is out of scope
for M1 and noted in the roadmap.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from masar.llm.base import Backend, BackendError, ChatParams, ChatResult, Message
from masar.policy.engine import ResolvedRoute


class Attempt(BaseModel):
    """One backend call attempt and its outcome."""

    model_config = ConfigDict(extra="forbid")

    model_name: str
    model_id: str
    ok: bool
    error: str | None = None


class DispatchOutcome(BaseModel):
    """A successful dispatch: the result plus how it was reached."""

    model_config = ConfigDict(extra="forbid")

    result: ChatResult
    model_name: str
    attempts: list[Attempt] = Field(min_length=1)
    latency_ms: float
    fallback_used: bool


class DispatchError(RuntimeError):
    """Raised when every model in the route's chain failed.

    ``attempts`` records each failure in order and ``latency_ms`` the total time
    spent, so the API layer can log and account for a failed request.
    """

    def __init__(self, attempts: list[Attempt], latency_ms: float) -> None:
        self.attempts = attempts
        self.latency_ms = latency_ms
        summary = "; ".join(f"{a.model_name}: {a.error}" for a in attempts)
        super().__init__(f"all models failed: {summary}")


class Dispatcher:
    """Run a resolved route across the model backends with retries and fallback."""

    def __init__(
        self,
        backends: dict[str, Backend],
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._backends = backends
        self._clock = clock

    def dispatch(
        self,
        route: ResolvedRoute,
        messages: list[Message],
        params: ChatParams,
    ) -> DispatchOutcome:
        """Execute ``route`` and return the first successful result.

        Raises:
            DispatchError: if no model in the chain produced a result.
        """
        attempts: list[Attempt] = []
        start = self._clock()

        for model_name in route.chain:
            backend = self._backends.get(model_name)
            if backend is None:
                attempts.append(
                    Attempt(
                        model_name=model_name,
                        model_id="",
                        ok=False,
                        error="no backend registered for this model",
                    )
                )
                continue

            for _ in range(route.retries + 1):
                try:
                    result = backend.chat(messages, params, timeout=route.timeout_seconds)
                except BackendError as exc:
                    attempts.append(
                        Attempt(
                            model_name=model_name,
                            model_id=backend.model_id,
                            ok=False,
                            error=str(exc),
                        )
                    )
                    continue
                attempts.append(Attempt(model_name=model_name, model_id=backend.model_id, ok=True))
                latency_ms = (self._clock() - start) * 1000
                return DispatchOutcome(
                    result=result,
                    model_name=model_name,
                    attempts=attempts,
                    latency_ms=latency_ms,
                    fallback_used=any(not a.ok for a in attempts),
                )

        latency_ms = (self._clock() - start) * 1000
        raise DispatchError(attempts, latency_ms)
