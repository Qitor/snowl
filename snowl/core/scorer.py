"""Core scoring contract for metric maps, score context, declaration, and validation.

Framework role:
- Defines `Scorer.score(...) -> dict[str, Score]` and the shared `ScoreContext` metadata passed to scorers.
- Validates that scorer outputs are structurally safe for artifacts, compare views, and monitor summaries.

Runtime/usage wiring:
- Used directly by runtime scoring phase and by benchmark/built-in scorer implementations.

Change guardrails:
- Keep metric map semantics strict; loose validation here propagates invalid artifacts across the stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from snowl.core.declarations import declare
from snowl.core.task_result import TaskResult
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class Score:
    value: float
    explanation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreContext:
    task_id: str
    agent_id: str
    sample_id: str | None = None
    task_metadata: dict[str, Any] = field(default_factory=dict)
    sample_metadata: dict[str, Any] = field(default_factory=dict)


Trace = Mapping[str, Any]
ScoreMap = dict[str, Score]


class Scorer(Protocol):
    """Scorer contract; supports multiple metrics per trial."""

    scorer_id: str

    def score(
        self,
        task_result: TaskResult,
        trace: Trace,
        context: ScoreContext,
    ) -> ScoreMap: ...


def scorer(
    value: Any | None = None,
    *,
    scorer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Declare a scorer object/factory for eval autodiscovery."""

    if scorer_id is not None and (not isinstance(scorer_id, str) or not scorer_id.strip()):
        raise SnowlValidationError("Decorator @scorer(...): 'scorer_id' must be a non-empty string.")

    def _decorate(inner: Any) -> Any:
        declared_id = scorer_id.strip() if isinstance(scorer_id, str) and scorer_id.strip() else None
        if declared_id is not None and hasattr(inner, "scorer_id"):
            try:
                setattr(inner, "scorer_id", declared_id)
            except Exception:
                pass
        return declare(inner, kind="scorer", object_id=declared_id, metadata=metadata)

    if value is not None:
        return _decorate(value)
    return _decorate


def validate_scores(scores: Mapping[str, Score]) -> None:
    if not scores:
        raise SnowlValidationError("Scorer returned no metrics; expected at least one.")

    for metric_name, score in scores.items():
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise SnowlValidationError("Metric names must be non-empty strings.")

        if not isinstance(score, Score):
            raise SnowlValidationError(
                f"Metric '{metric_name}' must map to a Score instance."
            )


def validate_scorer(scorer: Any) -> None:
    scorer_id = getattr(scorer, "scorer_id", None)
    if not isinstance(scorer_id, str) or not scorer_id.strip():
        raise SnowlValidationError("Scorer must define a non-empty 'scorer_id'.")

    score_fn = getattr(scorer, "score", None)
    if score_fn is None or not callable(score_fn):
        raise SnowlValidationError("Scorer must implement callable 'score(...)'.")
