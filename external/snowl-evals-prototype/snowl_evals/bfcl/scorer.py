"""BFCL scorer using Snowl function-call primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.scorer import function_call_match, grouped_metrics


@dataclass(frozen=True)
class BFCLScorer:
    scorer_id: str = "bfcl"

    def score(self, task_result: TaskResult, trace: Mapping[str, Any], context: ScoreContext) -> dict[str, Score]:
        scores = function_call_match(metric_name="function_call_accuracy").score(task_result, trace, context)
        base = scores["function_call_accuracy"]
        scores.update(grouped_metrics("function_call_accuracy", base, context, "category_name"))
        return scores
