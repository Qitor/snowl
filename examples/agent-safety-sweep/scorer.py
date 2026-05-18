"""Routing scorer for the agent-safety-sweep example.

Dispatches to the appropriate benchmark scorer based on the
benchmark name in task metadata.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from snowl.benchmarks.agentharm import AgentHarmScorer
from snowl.benchmarks.agentdojo import AgentDojoScorer
from snowl.benchmarks.toolemu import ToolEmuScorer
from snowl.core import Score, ScoreContext, TaskResult, scorer as declare_scorer
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig


def _judge_client_factory(model_name: str) -> OpenAICompatibleChatClient:
    return OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            provider_id=os.environ.get("SNOWL_JUDGE_PROVIDER_ID", "inf"),
            base_url=os.environ["SNOWL_JUDGE_BASE_URL"],
            api_key=os.environ["SNOWL_PROVIDER_API_KEY"],
            model=model_name,
            timeout=int(os.environ.get("SNOWL_JUDGE_TIMEOUT", "120")),
            max_retries=int(os.environ.get("SNOWL_JUDGE_MAX_RETRIES", "2")),
        )
    )


_JUDGE_MODEL = "ds-v4-flash"


@dataclass
class SafetySweepRoutingScorer:
    scorer_id: str = "safety_sweep_routing"
    _cache: dict[str, Any] = field(default_factory=dict)

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        benchmark = str(context.task_metadata.get("benchmark") or "").strip()
        scorer = self._resolve(benchmark)
        return scorer.score(task_result, trace, context)

    def _resolve(self, benchmark: str):
        if benchmark in self._cache:
            return self._cache[benchmark]

        if benchmark in ("agentharm", "agentharm_benign"):
            scorer = AgentHarmScorer(
                model_name=_JUDGE_MODEL,
                client_factory=_judge_client_factory,
            )
        elif benchmark == "agentdojo":
            scorer = AgentDojoScorer()
        elif benchmark == "toolemu":
            scorer = ToolEmuScorer()
        else:
            raise RuntimeError(
                f"SafetySweepRoutingScorer does not support benchmark '{benchmark}'."
            )

        self._cache[benchmark] = scorer
        return scorer


@declare_scorer()
def scorer() -> SafetySweepRoutingScorer:
    return SafetySweepRoutingScorer()
