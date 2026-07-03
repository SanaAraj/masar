"""The routing table, loaded and validated from YAML.

A :class:`RoutingConfig` describes *how* to route: a registry of models (each
flagged sovereign-hosted or not, with cost metadata) and an ordered list of
routes mapping ``(sensitivity, language, task)`` to a primary model and a
fallback chain. All invariants are checked at load time so a misconfigured
table fails loudly at startup rather than mid-request. The central invariant is
sovereignty: a route marked ``sovereign`` may only reference sovereign-hosted
models.

Routing here is heuristic (operational rules only). No field in this schema
carries a measured capability score; capability-aware routing arrives with
mizan-evals M2 data.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from masar.domain import LanguageClass, SensitivityClass, TaskType

ANY = "*"
_SUPPORTED_BACKENDS = frozenset({"mock", "openai"})
_MATCH_FIELDS: dict[str, frozenset[str]] = {
    "sensitivity": frozenset(s.value for s in SensitivityClass),
    "language": frozenset(v.value for v in LanguageClass),
    "task": frozenset(t.value for t in TaskType),
}


class ConfigError(ValueError):
    """Raised when a routing configuration is missing or invalid."""


class ModelSpec(BaseModel):
    """One model in the registry.

    ``name`` is the logical handle referenced by routes; ``model_id`` is the
    exact id passed to the backend (a provider model id, ideally dated/pinned).
    ``sovereign`` marks the model as sovereign-hosted. ``api_key_env`` and
    ``base_url_env`` name the environment variables holding credentials and
    endpoint, so secrets never live in the config. Costs are per 1,000 tokens in
    USD and must come from a cited source (see :attr:`RoutingConfig.cost_source`);
    the mock backend is truthfully priced at ``0.0``.
    """

    # `model_id`/`model_config` sit in pydantic's protected namespace; the domain
    # name is worth keeping, so the namespace guard is disabled explicitly.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(min_length=1)
    backend: str = "mock"
    model_id: str = Field(min_length=1)
    sovereign: bool = False
    base_url_env: str | None = None
    api_key_env: str | None = None
    cost_per_1k_input_usd: float = Field(default=0.0, ge=0.0)
    cost_per_1k_output_usd: float = Field(default=0.0, ge=0.0)

    @field_validator("backend")
    @classmethod
    def _known_backend(cls, value: str) -> str:
        if value not in _SUPPORTED_BACKENDS:
            raise ValueError(
                f"unknown backend {value!r} (expected one of {sorted(_SUPPORTED_BACKENDS)})"
            )
        return value


class RouteMatch(BaseModel):
    """The predicate a request must satisfy to take a route.

    Each field is either a concrete class value or ``"*"`` (matches anything).
    A match with all three fields ``"*"`` is a catch-all.
    """

    model_config = ConfigDict(extra="forbid")

    sensitivity: str = ANY
    language: str = ANY
    task: str = ANY

    @model_validator(mode="after")
    def _valid_values(self) -> RouteMatch:
        for field, allowed in _MATCH_FIELDS.items():
            value = getattr(self, field)
            if value != ANY and value not in allowed:
                raise ValueError(
                    f"match.{field}={value!r} is not valid; "
                    f"expected {ANY!r} or one of {sorted(allowed)}"
                )
        return self

    @property
    def is_catch_all(self) -> bool:
        """True when this predicate matches every request."""
        return self.sensitivity == ANY and self.language == ANY and self.task == ANY


class Route(BaseModel):
    """One routing rule: a predicate and the model chain that serves it.

    ``sovereign`` asserts that this route handles sovereign traffic; the config
    validator then requires every model in :attr:`chain` to be sovereign-hosted.
    ``timeout_seconds`` and ``retries`` override the table defaults for this route.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    match: RouteMatch = Field(default_factory=RouteMatch)
    primary: str = Field(min_length=1)
    fallbacks: list[str] = Field(default_factory=list)
    sovereign: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0)
    retries: int | None = Field(default=None, ge=0)

    @property
    def chain(self) -> list[str]:
        """The model names to try in order: primary first, then fallbacks."""
        return [self.primary, *self.fallbacks]


class RoutingDefaults(BaseModel):
    """Per-route defaults applied when a route does not override them."""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=30.0, gt=0)
    retries: int = Field(default=1, ge=0)


class RoutingConfig(BaseModel):
    """A validated routing table.

    ``label`` is the human-facing provenance string surfaced in ``/stats`` and the
    README; in this milestone it must announce the table as heuristic and pending
    mizan data. ``cost_source`` documents where non-zero prices came from.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    version: int = 0
    label: str = Field(min_length=1)
    models: list[ModelSpec] = Field(min_length=1)
    routes: list[Route] = Field(min_length=1)
    defaults: RoutingDefaults = Field(default_factory=RoutingDefaults)
    cost_source: str = ""

    @model_validator(mode="after")
    def _check_integrity(self) -> RoutingConfig:
        names = [m.name for m in self.models]
        if len(names) != len(set(names)):
            raise ValueError("model names must be unique within the registry")

        route_names = [r.name for r in self.routes]
        if len(route_names) != len(set(route_names)):
            raise ValueError("route names must be unique within the table")

        by_name = {m.name: m for m in self.models}
        for route in self.routes:
            for referenced in route.chain:
                if referenced not in by_name:
                    raise ValueError(
                        f"route {route.name!r} references unknown model {referenced!r}"
                    )
            if route.sovereign:
                offenders = [name for name in route.chain if not by_name[name].sovereign]
                if offenders:
                    raise ValueError(
                        f"sovereign route {route.name!r} may only route to sovereign-hosted "
                        f"models; these are not sovereign: {offenders}"
                    )

        catch_all_index = next((i for i, r in enumerate(self.routes) if r.match.is_catch_all), None)
        if catch_all_index is None:
            raise ValueError(
                "routing table needs a catch-all route (match sensitivity/language/task all "
                f"{ANY!r}) so every request is routable"
            )
        dead = [r.name for r in self.routes[catch_all_index + 1 :]]
        if dead:
            raise ValueError(
                f"routes after the catch-all {self.routes[catch_all_index].name!r} are "
                f"unreachable: {dead}"
            )
        return self

    def spec_for(self, model_name: str) -> ModelSpec:
        """Return the registry entry for ``model_name``.

        Raises:
            KeyError: if no model with that name is registered.
        """
        for model in self.models:
            if model.name == model_name:
                return model
        raise KeyError(f"no model named {model_name!r} in the registry")

    def timeout_for(self, route: Route) -> float:
        """The effective per-attempt timeout for ``route``, in seconds."""
        if route.timeout_seconds is not None:
            return route.timeout_seconds
        return self.defaults.timeout_seconds

    def retries_for(self, route: Route) -> int:
        """The effective retry count for ``route`` (attempts = retries + 1)."""
        return route.retries if route.retries is not None else self.defaults.retries


def load_config(path: str | Path) -> RoutingConfig:
    """Load and validate a routing table from a YAML file.

    Raises:
        ConfigError: if the file is missing, is not valid YAML, is not a mapping,
            or does not satisfy the :class:`RoutingConfig` schema (including the
            sovereignty invariant).
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"routing config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level YAML must be a mapping, got {type(raw).__name__}")
    try:
        return RoutingConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path}: invalid routing configuration: {exc}") from exc
