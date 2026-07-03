"""The policy engine: turn a classification into a concrete route.

Routes are evaluated top-to-bottom and the first whose predicate matches wins,
so ordering encodes priority (sovereign routes are placed first). The engine
resolves per-route timeout and retry defaults into a :class:`ResolvedRoute` that
the dispatcher can execute without consulting the config again.

Routing keys are ``(sensitivity, language, task)`` only. The dialect signal on a
classification is carried for logging but is not consulted here; capability- and
dialect-aware routing arrive with mizan-evals M2 data.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from masar.config import ANY, RouteMatch, RoutingConfig
from masar.domain import Classification


class PolicyError(RuntimeError):
    """Raised when no route matches a request (a table without a catch-all)."""


class ResolvedRoute(BaseModel):
    """A matched route with its timeout and retry policy resolved.

    ``chain`` lists the model names to try in order (primary first). ``sovereign``
    echoes the route's sovereignty assertion for logging and downstream checks.
    """

    model_config = ConfigDict(extra="forbid")

    route_name: str
    sovereign: bool
    chain: list[str] = Field(min_length=1)
    timeout_seconds: float
    retries: int


class PolicyEngine:
    """Resolve classifications to routes against a validated routing table."""

    def __init__(self, config: RoutingConfig) -> None:
        self._config = config

    @staticmethod
    def _matches(match: RouteMatch, classification: Classification) -> bool:
        return (
            match.sensitivity in (ANY, classification.sensitivity.value)
            and match.language in (ANY, classification.language.value)
            and match.task in (ANY, classification.task.value)
        )

    def resolve(self, classification: Classification) -> ResolvedRoute:
        """Return the first route matching ``classification``.

        Raises:
            PolicyError: if no route matches. A validated config always contains
                a catch-all, so this indicates the engine was handed an
                unvalidated table.
        """
        for route in self._config.routes:
            if self._matches(route.match, classification):
                return ResolvedRoute(
                    route_name=route.name,
                    sovereign=route.sovereign,
                    chain=route.chain,
                    timeout_seconds=self._config.timeout_for(route),
                    retries=self._config.retries_for(route),
                )
        raise PolicyError("no route matched; routing table has no catch-all")
