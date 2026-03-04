"""TerminalBench benchmark-specific scorer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.scorer import UnitTestResultScorer


@dataclass
class TerminalBenchScorer:
    metric_name: str = "accuracy"
    pass_rate_metric_name: str = "pass_rate"
    scorer_id: str = "terminalbench"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        scorer = UnitTestResultScorer(
            metric_name=self.metric_name,
            pass_rate_metric_name=self.pass_rate_metric_name,
            parser_results_trace_event="terminalbench.parser_results",
        )
        return scorer.score(task_result, trace, context)


def terminalbench() -> TerminalBenchScorer:
    return TerminalBenchScorer()
