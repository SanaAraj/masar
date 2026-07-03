"""masar: an eval-driven, sovereignty-aware LLM router.

masar is an OpenAI-compatible FastAPI gateway. Each request is classified
(data sensitivity, language, task type), matched against a YAML routing table,
and dispatched to a primary model with a fallback chain, while tokens, cost, and
latency are accounted per route and model.

The package is organised into small, independent layers:

- :mod:`masar.domain` - the classification vocabulary (sensitivity, language,
  task, dialect) shared across the router.
- :mod:`masar.config` - the routing table loaded and validated from YAML,
  including the sovereignty invariant enforced at startup.
- :mod:`masar.classify` - the pluggable, rule-based v0 request classifier.
- :mod:`masar.policy` - the policy engine mapping a classification to a route.
- :mod:`masar.llm` - chat backends (mock + OpenAI-compatible) built from config,
  reading keys from the environment.
- :mod:`masar.dispatch` - primary/fallback dispatch with retries and timeouts.
- :mod:`masar.accounting` - cost and latency accounting with an in-memory stats
  store.
- :mod:`masar.api` - the OpenAI-compatible HTTP surface.

Routing in this milestone is heuristic (operational rules only). No routing rule
references a measured capability score; capability-aware routing arrives with
mizan-evals M2 data.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
