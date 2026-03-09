from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.toolemu import ToolEmuScorer, build_tool_emu_llm
from snowl.benchmarks.toolemu.runtime import persist_tool_emu_scores
from snowl.core import scorer as declare_scorer
from snowl.core import Score, ScoreContext, TaskResult
from snowl.utils.env import env_optional_int, env_str


PROJECT_DIR = Path(__file__).resolve().parent


class SavingToolEmuScorer(ToolEmuScorer):
    def score(
        self,
        task_result: TaskResult,
        trace: dict,
        context: ScoreContext,
    ) -> dict[str, Score]:
        scores = super().score(task_result, trace, context)
        trace_events = trace.get("trace_events", []) if isinstance(trace, dict) else []
        case_name = None
        for event in trace_events:
            if not isinstance(event, dict):
                continue
            if str(event.get("event")) != "toolemu.emulation":
                continue
            case_name = str(event.get("case_name") or "") or None
            break
        persist_tool_emu_scores(
            project_dir=PROJECT_DIR,
            sample_id=context.sample_id,
            case_name=case_name,
            scores={
                metric: {
                    "value": score.value,
                    "explanation": score.explanation,
                    "metadata": score.metadata,
                }
                for metric, score in scores.items()
            },
            extra={"task_id": context.task_id, "agent_id": context.agent_id},
        )
        return scores


@declare_scorer()
def scorer() -> ToolEmuScorer:
    evaluator_llm = build_tool_emu_llm(
        "evaluator",
        model_name=env_str("SNOWL_TOOLEMU_EVALUATOR_MODEL", "Qwen/Qwen3-8B"),
        openai_api_key=(env_str("SNOWL_TOOLEMU_EVALUATOR_API_KEY") or ""),
        openai_api_base=(
            env_str("SNOWL_TOOLEMU_EVALUATOR_BASE_URL", "https://api.siliconflow.cn/v1")
            or "https://api.siliconflow.cn/v1"
        ),
        max_tokens=env_optional_int("SNOWL_TOOLEMU_EVALUATOR_MAX_TOKENS"),
    )
    return SavingToolEmuScorer(evaluator_llm=evaluator_llm)
