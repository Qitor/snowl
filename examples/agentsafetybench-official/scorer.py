from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.agentsafetybench import AgentSafetyBenchScorer, persist_agentsafetybench_scores
from snowl.core import Score, ScoreContext, TaskResult, scorer as declare_scorer
from snowl.project_config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT = load_project_config(PROJECT_DIR)
ASB_SETTINGS = PROJECT.benchmark_settings("agentsafetybench")
DEFAULT_SHIELD_MODEL_PATH = "thu-coai/ShieldAgent"
DEFAULT_SHIELD_MODEL_BASE = "qwen"


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
            output_dir=ASB_SETTINGS.get("output_dir"),
            run_stamp=str(ASB_SETTINGS.get("run_stamp") or ""),
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
        shield_model_path=str(ASB_SETTINGS.get("shield_model_path", DEFAULT_SHIELD_MODEL_PATH)),
        shield_model_base=str(ASB_SETTINGS.get("shield_model_base", DEFAULT_SHIELD_MODEL_BASE)),
        shield_batch_size=int(ASB_SETTINGS.get("shield_batch_size", 1)),
    )
