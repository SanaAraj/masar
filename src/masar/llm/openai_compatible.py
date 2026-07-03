"""Backend for any OpenAI-compatible ``/chat/completions`` endpoint.

One class serves a frontier model on ``api.openai.com`` and any open model
exposed through an OpenAI-compatible provider; they differ only by ``base_url``,
API key, and model id. Token usage is read from the provider's ``usage`` block
when present and estimated locally otherwise.
"""

from __future__ import annotations

import httpx

from masar.llm.base import (
    Backend,
    BackendError,
    BackendTimeout,
    ChatParams,
    ChatResult,
    Message,
    approx_token_count,
)


class OpenAICompatibleBackend(Backend):
    """Call a chat-completions endpoint over HTTP.

    Args:
        model_id: exact provider model id (recorded in results).
        base_url: endpoint root, e.g. ``https://api.openai.com/v1``.
        api_key: bearer token for the provider.
        client: optional pre-built ``httpx.Client`` (inject a mock transport in
            tests); a default client is created when omitted.
        timeout: default request timeout in seconds, used when a call does not
            supply its own.
    """

    def __init__(
        self,
        model_id: str,
        *,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return self._model_id

    def chat(
        self,
        messages: list[Message],
        params: ChatParams,
        timeout: float | None = None,
    ) -> ChatResult:
        payload: dict[str, object] = {
            "model": self._model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.seed is not None:
            payload["seed"] = params.seed

        request_timeout = self._default_timeout if timeout is None else timeout
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=request_timeout,
            )
        except httpx.TimeoutException as exc:
            raise BackendTimeout(
                f"{self._model_id}: request timed out after {request_timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"{self._model_id}: request failed: {exc}") from exc

        if response.status_code != 200:
            raise BackendError(
                f"{self._model_id}: HTTP {response.status_code} from {self._base_url}: "
                f"{response.text[:500]}"
            )

        return self._parse(response.json(), messages)

    def _parse(self, body: dict, messages: list[Message]) -> ChatResult:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"{self._model_id}: unexpected response shape: {body!r}") from exc
        if content is None:
            raise BackendError(f"{self._model_id}: response contained no content")
        content = str(content)

        usage = body.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        estimated = prompt_tokens is None or completion_tokens is None
        if estimated:
            prompt_tokens = sum(approx_token_count(m.content) for m in messages)
            completion_tokens = approx_token_count(content)

        return ChatResult(
            text=content,
            model_id=self._model_id,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            usage_estimated=estimated,
        )
