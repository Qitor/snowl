from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from snowl.benchmarks.agentharm import AgentHarmScorer
from snowl.benchmarks.coconot import CoconotScorer
from snowl.benchmarks.fortress import FortressAdversarialScorer, FortressBenignScorer
from snowl.benchmarks.xstest import XSTestScorer
from snowl.core import Score, ScoreContext, TaskResult, scorer as declare_scorer
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.scorer.choice import ChoiceAnswerScorer


_CHOICE_BENCHMARKS = {
    "cybermetric_80",
    "cybermetric_500",
    "cybermetric_2000",
    "cybermetric_10000",
    "sec_qa_v1",
    "sec_qa_v2",
    "sevenllm_mcq_en",
    "sevenllm_mcq_zh",
}


def _api_key() -> str:
    key = os.getenv("SNOWL_SMOKE_API_KEY", "").strip() or os.getenv("INF_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set SNOWL_SMOKE_API_KEY or INF_API_KEY before running this example.")
    return key


def _judge_model() -> str:
    return os.getenv("SNOWL_SMOKE_JUDGE_MODEL", "deepseek-v3-ep").strip() or "deepseek-v3-ep"


def _judge_base_url() -> str:
    return os.getenv("SNOWL_SMOKE_JUDGE_BASE_URL", "http://dsv3.sii.edu.cn/v1").strip()


def _judge_models() -> list[str]:
    raw = os.getenv("SNOWL_SMOKE_JUDGE_MODELS", "").strip()
    if not raw:
        return [_judge_model()]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _client_factory(model_name: str) -> OpenAICompatibleChatClient:
    return OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            provider_id="remote-smoke",
            base_url=_judge_base_url(),
            api_key=_api_key(),
            model=model_name,
            timeout=120,
            max_retries=1,
        )
    )


@dataclass
class SafetyBenchmarkRoutingScorer:
    scorer_id: str = "safety_benchmark_routing"
    _cache: dict[str, Any] = field(default_factory=dict)

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        benchmark = str(context.task_metadata.get("benchmark") or "").strip()
        scorer = self._resolve(benchmark, context)
        return scorer.score(task_result, trace, context)

    def _resolve(self, benchmark: str, context: ScoreContext):
        key = f"{benchmark}:{context.task_metadata.get('subset')}:{context.task_metadata.get('mode')}"
        if key in self._cache:
            return self._cache[key]
        if benchmark == "xstest":
            scorer = XSTestScorer(model_name=_judge_model(), client_factory=_client_factory)
        elif benchmark == "coconot":
            scorer = CoconotScorer(
                model_name=_judge_model(),
                subset=str(context.task_metadata.get("subset") or "original"),
                client_factory=_client_factory,
            )
        elif benchmark == "fortress_adversarial":
            scorer = FortressAdversarialScorer(
                model_names=_judge_models(),
                client_factory=_client_factory,
            )
        elif benchmark == "fortress_benign":
            scorer = FortressBenignScorer(model_name=_judge_model(), client_factory=_client_factory)
        elif benchmark in {"agentharm", "agentharm_benign"}:
            scorer = AgentHarmScorer(model_name=_judge_model(), client_factory=_client_factory)
        elif benchmark in _CHOICE_BENCHMARKS:
            scorer = ChoiceAnswerScorer()
        else:
            raise RuntimeError(
                f"SafetyBenchmarkRoutingScorer does not support benchmark '{benchmark}'."
            )
        self._cache[key] = scorer
        return scorer


@declare_scorer()
def scorer() -> SafetyBenchmarkRoutingScorer:
    return SafetyBenchmarkRoutingScorer()
