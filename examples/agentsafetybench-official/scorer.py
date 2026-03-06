from __future__ import annotations

import os
from pathlib import Path

from snowl.benchmarks.agentsafetybench import AgentSafetyBenchScorer, persist_agentsafetybench_scores
from snowl.core import Score, ScoreContext, TaskResult, scorer as declare_scorer


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SHIELD_MODEL_PATH = "thu-coai/ShieldAgent"
DEFAULT_SHIELD_MODEL_BASE = "qwen"


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


class SavingAgentSafetyBenchScorer(AgentSafetyBenchScorer):
    def score(
        self,
        task_result: TaskResult,
        trace: dict,
        context: ScoreContext,
    ) -> dict[str, Score]:
        scores = super().score(task_result, trace, context)
        case_id = None
        for event in trace.get("trace_events", []):
            if not isinstance(event, dict):
                continue
            if str(event.get("event")) != "agentsafetybench.execution":
                continue
            case_id = event.get("case_id")
            break
        persist_agentsafetybench_scores(
            project_dir=PROJECT_DIR,
            sample_id=context.sample_id,
            case_id=case_id,
            scores={
                "sample_id": context.sample_id,
                "case_id": case_id,
                "task_id": context.task_id,
                "agent_id": context.agent_id,
                "scores": {
                    metric: {
                        "value": score.value,
                        "explanation": score.explanation,
                        "metadata": score.metadata,
                    }
                    for metric, score in scores.items()
                },
            },
        )
        return scores


@declare_scorer()
def scorer() -> AgentSafetyBenchScorer:
    return SavingAgentSafetyBenchScorer(
        shield_model_path=_env_str("SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_PATH", DEFAULT_SHIELD_MODEL_PATH),
        shield_model_base=_env_str("SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_BASE", DEFAULT_SHIELD_MODEL_BASE),
        shield_batch_size=int(_env_str("SNOWL_AGENTSAFETYBENCH_SHIELD_BATCH_SIZE", "1")),
    )
