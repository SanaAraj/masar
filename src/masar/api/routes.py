"""HTTP routes: the chat-completions gateway, stats, and health.

The chat handler is the whole pipeline in one place: classify, resolve a route,
dispatch with fallback, then account and log. Routing metadata rides back on
``X-Masar-*`` response headers so an OpenAI client sees a standard body while an
operator can still see how the request was routed. Handlers are synchronous, so
FastAPI runs them in its thread pool and the synchronous dispatch never blocks
the event loop.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from masar.accounting import estimate_cost
from masar.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ResponseMessage,
    Usage,
)
from masar.classify.base import ClassifierInput
from masar.dispatch import DispatchError
from masar.llm.base import ChatParams, Message
from masar.observability import decision_record, log_request

router = APIRouter()


def _request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


def _joined_text(messages: list) -> str:
    return "\n".join(m.content for m in messages if m.content)


def _llm_messages(messages: list) -> list[Message]:
    return [Message(role=m.role, content=m.content or "") for m in messages]


@router.get("/healthz")
def healthz() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/stats")
def stats(request: Request) -> dict:
    """Aggregated accounting by route and model, with routing provenance."""
    state = request.app.state
    snapshot = state.stats.snapshot()
    return {
        "routing_label": state.config.label,
        "cost_source": state.config.cost_source,
        **snapshot.model_dump(),
    }


@router.post("/v1/chat/completions", response_model=None)
def chat_completions(
    request: Request, body: ChatCompletionRequest, response: Response
) -> ChatCompletionResponse | JSONResponse:
    """Route a chat request to a model and return an OpenAI-compatible response."""
    if body.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported in M1")

    state = request.app.state
    request_id = _request_id()

    classification = state.classifier.classify(
        ClassifierInput(text=_joined_text(body.messages), has_tools=bool(body.tools))
    )
    resolved = state.engine.resolve(classification)

    params = ChatParams(
        temperature=body.temperature,
        max_tokens=body.max_tokens or 512,
        seed=body.seed,
    )

    try:
        outcome = state.dispatcher.dispatch(resolved, _llm_messages(body.messages), params)
    except DispatchError as exc:
        state.stats.record_failure(route=resolved.route_name, latency_ms=exc.latency_ms)
        log_request(
            decision_record(
                request_id=request_id,
                classification=classification,
                route_name=resolved.route_name,
                served_model=None,
                attempts=exc.attempts,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                latency_ms=exc.latency_ms,
                ok=False,
            )
        )
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "upstream_error"}},
            headers={"X-Masar-Route": resolved.route_name, "X-Masar-Request-Id": request_id},
        )

    result = outcome.result
    spec = state.config.spec_for(outcome.model_name)
    cost = estimate_cost(spec, result.prompt_tokens, result.completion_tokens)

    state.stats.record(
        route=resolved.route_name,
        model=outcome.model_name,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=cost,
        latency_ms=outcome.latency_ms,
        ok=True,
    )
    log_request(
        decision_record(
            request_id=request_id,
            classification=classification,
            route_name=resolved.route_name,
            served_model=outcome.model_name,
            attempts=outcome.attempts,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cost_usd=cost,
            latency_ms=outcome.latency_ms,
            ok=True,
        )
    )

    response.headers["X-Masar-Request-Id"] = request_id
    response.headers["X-Masar-Route"] = resolved.route_name
    response.headers["X-Masar-Model"] = outcome.model_name
    response.headers["X-Masar-Classification"] = (
        f"{classification.sensitivity.value}/{classification.language.value}/"
        f"{classification.task.value}"
    )
    response.headers["X-Masar-Cost-USD"] = f"{cost:.6f}"
    response.headers["X-Masar-Latency-Ms"] = f"{outcome.latency_ms:.3f}"
    response.headers["X-Masar-Fallback-Used"] = "true" if outcome.fallback_used else "false"

    return ChatCompletionResponse(
        id=request_id,
        created=int(time.time()),
        model=result.model_id,
        choices=[Choice(message=ResponseMessage(content=result.text))],
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        ),
    )
