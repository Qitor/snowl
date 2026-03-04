from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.core import Score
from snowl.eval import run_eval
from snowl.ui import EventPhase, TaskExecutionStatus, TaskMonitor, build_score_explanations, normalize_ui_event


def test_normalize_ui_event_assigns_required_fields_and_phase() -> None:
    evt = normalize_ui_event(
        {"event": "runtime.scorer.finish", "task_id": "t1", "agent_id": "a1", "variant_id": "v1", "message": "ok"},
        run_id="run-1",
        ts_ms=123,
    )
    payload = evt.to_dict()
    assert payload["run_id"] == "run-1"
    assert payload["ts_ms"] == 123
    assert payload["phase"] == EventPhase.SCORER.value
    assert payload["task_id"] == "t1"
    assert payload["agent_id"] == "a1"
    assert payload["variant_id"] == "v1"


def test_task_monitor_transitions_from_queue_to_finish() -> None:
    monitor = TaskMonitor()
    monitor.upsert_queued(task_id="t1", agent_id="a1", variant_id="v1", sample_id="s1")
    monitor.apply_event(
        normalize_ui_event(
            {"event": "runtime.trial.start", "task_id": "t1", "agent_id": "a1", "variant_id": "v1", "sample_id": "s1"},
            run_id="run-1",
            ts_ms=100,
        )
    )
    monitor.apply_event(
        normalize_ui_event(
            {"event": "runtime.scorer.start", "task_id": "t1", "agent_id": "a1", "variant_id": "v1", "sample_id": "s1"},
            run_id="run-1",
            ts_ms=150,
        )
    )
    monitor.apply_event(
        normalize_ui_event(
            {
                "event": "runtime.scorer.finish",
                "task_id": "t1",
                "agent_id": "a1",
                "variant_id": "v1",
                "sample_id": "s1",
                "metrics": {"accuracy": 0.5},
            },
            run_id="run-1",
            ts_ms=160,
        )
    )
    monitor.apply_event(
        normalize_ui_event(
            {"event": "runtime.trial.finish", "task_id": "t1", "agent_id": "a1", "variant_id": "v1", "sample_id": "s1", "status": "incorrect"},
            run_id="run-1",
            ts_ms=200,
        )
    )
    state = monitor.list_states()[0]
    assert state.status == TaskExecutionStatus.INCORRECT
    assert state.duration_ms == 100
    assert state.scorer_metrics["accuracy"] == 0.5


def test_build_score_explanations_extracts_judge_evidence() -> None:
    scores = {
        "judge": Score(
            value=0.25,
            explanation="refusal not detected",
            metadata={
                "judge_prompt": "prompt text",
                "judge_system_prompt": "system text",
                "judge_parsed": {"reasoning": "x", "score": 0.25},
            },
        )
    }
    exps = build_score_explanations(scores, task_result={"status": "incorrect"})
    assert len(exps) == 1
    assert exps[0].metric == "judge"
    assert any("judge_prompt=" in item for item in exps[0].evidence)
    assert any("judge_parsed=" in item for item in exps[0].evidence)


def test_eval_profiling_contains_task_monitor_snapshot(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content":"ok"},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state
agent = A()
""",
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score
class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0, explanation="ok")}
scorer = S()
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None))
    profiling = json.loads((Path(result.artifacts_dir) / "profiling.json").read_text(encoding="utf-8"))
    states = profiling.get("task_monitor", [])
    assert len(states) == 1
    assert states[0]["task_id"] == "t1"
    assert states[0]["status"] == "success"
