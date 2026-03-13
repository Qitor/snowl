"""Benchmark-specific scorer implementation for `terminalbench`.

Framework role:
- Translates normalized task results and traces into benchmark-native metric outputs.

Runtime/usage wiring:
- Used as scorer layer in benchmark runs for this dataset family.
- Key top-level symbols in this file: `TerminalBenchScorer`, `terminalbench`.

Change guardrails:
- Metric semantics here define benchmark comparability across runs; change carefully.
"""

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
