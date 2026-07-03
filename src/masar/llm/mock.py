"""A deterministic mock backend for tests, offline development, and the demo.

The mock never touches the network, so the whole gateway is runnable and
testable without API keys. Output and token counts are a deterministic function
of the model id and the messages, which lets tests assert exact values.
"""

from __future__ import annotations

import hashlib

from masar.llm.base import Backend, ChatParams, ChatResult, Message, approx_token_count


class MockBackend(Backend):
    """A backend returning canned or deterministically-synthesised text.

    Args:
        model_id: identifier reported in results.
        scripted: optional exact ``rendered-prompt -> response`` overrides, where
            the rendered prompt is ``"role: content"`` lines joined by newlines.

    The ``calls`` counter records how many times :meth:`chat` actually ran, so
    tests and the dispatcher's fallback logic can be exercised precisely.
    """

    def __init__(self, model_id: str = "mock-1", scripted: dict[str, str] | None = None) -> None:
        self._model_id = model_id
        self._scripted = dict(scripted or {})
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    def _render(self, messages: list[Message]) -> str:
        return "\n".join(f"{m.role}: {m.content}" for m in messages)

    def chat(
        self,
        messages: list[Message],
        params: ChatParams,
        timeout: float | None = None,
    ) -> ChatResult:
        self.calls += 1
        prompt = self._render(messages)
        if prompt in self._scripted:
            text = self._scripted[prompt]
        else:
            digest = hashlib.sha256(
                f"{self._model_id}\x00{prompt}\x00{params.temperature}\x00{params.seed}".encode()
            ).hexdigest()[:16]
            text = f"[mock:{self._model_id}] {digest}"
        return ChatResult(
            text=text,
            model_id=self._model_id,
            prompt_tokens=sum(approx_token_count(m.content) for m in messages),
            completion_tokens=approx_token_count(text),
        )
