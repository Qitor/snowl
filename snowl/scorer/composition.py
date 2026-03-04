"""Composable scorer primitives (weighted + chained)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult


@dataclass(frozen=True)
class WeightedCompositeScorer:
    scorers: list[Any]
    weights: dict[str, float]
    metric_name: str = "weighted_score"
    scorer_id: str = "weighted_composite"
    strict: bool = False

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        merged: dict[str, Score] = {}
        weighted_sum = 0.0
        total_weight = 0.0
        errors: list[dict[str, str]] = []

        for scorer in self.scorers:
            sid = str(getattr(scorer, "scorer_id", scorer.__class__.__name__))
            try:
                out = scorer.score(task_result, trace, context)
            except Exception as exc:
                if self.strict:
                    raise
                errors.append({"scorer_id": sid, "error": str(exc)})
                continue

            for name, score in dict(out).items():
                merged[name] = score
                key = f"{sid}.{name}"
                if key not in self.weights:
                    continue
                weight = float(self.weights[key])
                weighted_sum += float(score.value) * weight
                total_weight += weight

        value = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        merged[self.metric_name] = Score(
            value=value,
            explanation=f"weighted composite from {len(self.scorers)} scorers",
            metadata={
                "total_weight": total_weight,
                "weighted_sum": weighted_sum,
                "weights": dict(self.weights),
                "errors": errors,
            },
        )
        return merged


@dataclass(frozen=True)
class ChainedScorer:
    scorers: list[Any]
    namespace_metrics: bool = True
    scorer_id: str = "chained"
    strict: bool = False

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        merged: dict[str, Score] = {}
        errors: list[dict[str, str]] = []

        for scorer in self.scorers:
            sid = str(getattr(scorer, "scorer_id", scorer.__class__.__name__))
            try:
                out = scorer.score(task_result, trace, context)
            except Exception as exc:
                if self.strict:
                    raise
                errors.append({"scorer_id": sid, "error": str(exc)})
                continue

            for name, score in dict(out).items():
                key = f"{sid}.{name}" if self.namespace_metrics else name
                merged[key] = score

        if errors:
            merged["chain_error_count"] = Score(
                value=float(len(errors)),
                explanation="number of scorer failures in chain",
                metadata={"errors": errors},
            )
        return merged


def weighted(
    scorers: list[Any],
    *,
    weights: dict[str, float],
    metric_name: str = "weighted_score",
    strict: bool = False,
) -> WeightedCompositeScorer:
    return WeightedCompositeScorer(
        scorers=list(scorers),
        weights=dict(weights),
        metric_name=metric_name,
        strict=strict,
    )


def chain(
    scorers: list[Any],
    *,
    namespace_metrics: bool = True,
    strict: bool = False,
) -> ChainedScorer:
    return ChainedScorer(
        scorers=list(scorers),
        namespace_metrics=namespace_metrics,
        strict=strict,
    )

