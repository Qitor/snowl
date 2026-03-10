from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.toolemu import ToolEmuScorer, build_tool_emu_llm
from snowl.benchmarks.toolemu.runtime import persist_tool_emu_scores
from snowl.core import scorer as declare_scorer
from snowl.core import Score, ScoreContext, TaskResult
from snowl.project_config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT = load_project_config(PROJECT_DIR)
TOOLEMU_SETTINGS = PROJECT.benchmark_settings("toolemu")


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
            output_dir=TOOLEMU_SETTINGS.get("output_dir"),
            run_stamp=str(TOOLEMU_SETTINGS.get("run_stamp") or ""),
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
    if PROJECT.judge is None:
        raise RuntimeError("toolemu-official scorer requires judge.model in project.yml")
    evaluator_llm = build_tool_emu_llm(
        "evaluator",
        model_name=PROJECT.judge.model,
        openai_api_key=PROJECT.judge.config.api_key,
        openai_api_base=PROJECT.judge.config.base_url,
        request_timeout=int(PROJECT.judge.config.timeout),
        max_retries=PROJECT.judge.config.max_retries,
        max_tokens=(
            int(TOOLEMU_SETTINGS["evaluator_max_tokens"])
            if TOOLEMU_SETTINGS.get("evaluator_max_tokens") is not None
            else None
        ),
    )
    return SavingToolEmuScorer(evaluator_llm=evaluator_llm)
