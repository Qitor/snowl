"""Score reduction strategies for multi-epoch evaluation.

Framework role:
- Defines ScoreReducer protocol for aggregating scores across epochs.
- Provides MeanReducer, MaxReducer, and PassAtKReducer implementations.
- PassAtKReducer uses the unbiased estimator from Chen et al. (2021).

Runtime/usage wiring:
- Used by eval_loop when epochs > 1 to aggregate per-epoch scores.
- Resolved from project.yml via ``resolve_score_reducer()``.

Change guardrails:
- Must stay framework-independent (no third-party imports).
- Reducer output must be compatible with MetricAggregator input format.
"""

from __future__ import annotations

import math
from typing import Any, Protocol, Sequence, runtime_checkable

from snowl.core.scorer import Score
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# ScoreReducer Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ScoreReducer(Protocol):
    """Aggregate per-epoch scores into a single reduced score per metric."""

    reducer_id: str

    def reduce(self, scores: Sequence[dict[str, Score]]) -> dict[str, Score]:
        """Reduce a sequence of per-epoch score maps into one score map.

        Args:
            scores: One dict per epoch, each mapping metric_name -> Score.

        Returns:
            A single dict mapping metric_name -> Score with reduced values.
        """
        ...


# ---------------------------------------------------------------------------
# Built-in reducers
# ---------------------------------------------------------------------------

class MeanReducer:
    """Reduce by averaging score values across epochs."""

    reducer_id: str = "mean"

    def reduce(self, scores: Sequence[dict[str, Score]]) -> dict[str, Score]:
        if not scores:
            return {}
        metric_values: dict[str, list[float]] = {}
        for epoch_scores in scores:
            for name, score in epoch_scores.items():
                metric_values.setdefault(name, []).append(score.value)
        result: dict[str, Score] = {}
        for name, values in metric_values.items():
            mean_val = sum(values) / len(values)
            result[name] = Score(
                value=mean_val,
                explanation=f"mean of {len(values)} epochs",
                metadata={"epochs": len(values), "values": values},
            )
        return result


class MaxReducer:
    """Reduce by taking the maximum score value across epochs."""

    reducer_id: str = "max"

    def reduce(self, scores: Sequence[dict[str, Score]]) -> dict[str, Score]:
        if not scores:
            return {}
        metric_values: dict[str, list[float]] = {}
        for epoch_scores in scores:
            for name, score in epoch_scores.items():
                metric_values.setdefault(name, []).append(score.value)
        result: dict[str, Score] = {}
        for name, values in metric_values.items():
            result[name] = Score(
                value=max(values),
                explanation=f"max of {len(values)} epochs",
                metadata={"epochs": len(values), "values": values},
            )
        return result


class PassAtKReducer:
    """Compute pass@k: probability of at least one correct solution in k attempts.

    Uses the unbiased estimator from Chen et al. (2021):
        pass@k = 1 - C(n-c, k) / C(n, k)
    where n = total attempts, c = correct attempts, k = the k parameter.

    This reducer expects binary scores (0.0 or 1.0) as input.
    """

    reducer_id: str = "pass_at_k"

    def __init__(self, k: int = 1) -> None:
        if k < 1:
            raise ValueError("pass@k requires k >= 1")
        self.k = k

    def reduce(self, scores: Sequence[dict[str, Score]]) -> dict[str, Score]:
        if not scores:
            return {}
        metric_values: dict[str, list[float]] = {}
        for epoch_scores in scores:
            for name, score in epoch_scores.items():
                metric_values.setdefault(name, []).append(score.value)
        result: dict[str, Score] = {}
        for name, values in metric_values.items():
            n = len(values)
            c = sum(1 for v in values if v >= 1.0)
            k = min(self.k, n)
            pass_at_k = _compute_pass_at_k(n, c, k)
            result[name] = Score(
                value=pass_at_k,
                explanation=f"pass@{k} from {n} attempts ({c} correct)",
                metadata={"n": n, "c": c, "k": k, "values": values},
            )
        return result


# ---------------------------------------------------------------------------
# pass@k computation
# ---------------------------------------------------------------------------

def _compute_pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator for pass@k (Chen et al., 2021).

    pass@k = 1 - C(n-c, k) / C(n, k)

    Uses log-space to avoid overflow for large n and k.
    When n-c < k, pass@k = 1.0 (all samples can be correct).
    """
    if n - c < k:
        return 1.0
    if k == 0:
        return 1.0
    # log(C(n-c,k)) - log(C(n,k)) = sum_{i=0}^{k-1} [log(n-c-i) - log(n-i)]
    log_ratio = 0.0
    for i in range(k):
        log_ratio += math.log(n - c - i) - math.log(n - i)
    return 1.0 - math.exp(log_ratio)


# ---------------------------------------------------------------------------
# Validation and resolution
# ---------------------------------------------------------------------------

def validate_score_reducer(reducer: Any) -> None:
    """Validate a ScoreReducer instance."""
    if not hasattr(reducer, "reducer_id"):
        raise SnowlValidationError("ScoreReducer must define 'reducer_id'.")
    if not hasattr(reducer, "reduce") or not callable(reducer.reduce):
        raise SnowlValidationError("ScoreReducer must implement 'reduce()'.")


def resolve_score_reducer(
    reducer_name: str,
    *,
    epochs: int = 1,
    k: int | None = None,
) -> ScoreReducer | None:
    """Resolve a score reducer by name.

    Args:
        reducer_name: One of 'mean', 'max', 'pass_at_k'.
        epochs: Number of epochs (if <= 1, returns None since no reduction needed).
        k: The k parameter for pass@k (defaults to epochs if not specified).

    Returns:
        A ScoreReducer instance, or None if epochs <= 1.
    """
    if epochs <= 1:
        return None
    if reducer_name == "mean":
        return MeanReducer()
    elif reducer_name == "max":
        return MaxReducer()
    elif reducer_name == "pass_at_k":
        return PassAtKReducer(k=k if k is not None else epochs)
    else:
        raise SnowlValidationError(
            f"Unknown score reducer '{reducer_name}'. Must be 'mean', 'max', or 'pass_at_k'."
        )
