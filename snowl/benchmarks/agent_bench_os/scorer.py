"""AgentBench OS scorer built from Snowl primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult
from snowl.scorer import answer_match, command_check


@dataclass(frozen=True)
class AgentBenchOSScorer:
    scorer_id: str = "agent_bench_os"

    def score(self, task_result: TaskResult, trace: Mapping[str, Any], context: ScoreContext) -> dict[str, Score]:
        evaluation = context.sample_metadata.get("evaluation")
        if isinstance(evaluation, Mapping) and evaluation.get("match") is not None:
            scores = answer_match(metric_name="agent_bench_os_success").score(task_result, trace, context)
            return scores
        if context.sample_metadata.get("verification_command") or context.sample_metadata.get("check_command"):
            scores = command_check(metric_name="agent_bench_os_success").score(task_result, trace, context)
            return scores
        return {
            "agent_bench_os_success": Score(
                0.0,
                "No supported AgentBench OS scoring contract found.",
                {"evaluation": dict(evaluation) if isinstance(evaluation, Mapping) else evaluation},
            )
        }
