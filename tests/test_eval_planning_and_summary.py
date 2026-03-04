from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.eval import run_eval


def _write_project(tmp_path: Path, *, two_tasks: bool, two_agents: bool) -> None:
    task_extra = """
task2 = Task(
    task_id=\"t2\",
    env_spec=EnvSpec(env_type=\"local\"),
    sample_iter_factory=lambda: iter([{\"id\": \"s2\", \"input\": \"y\"}]),
)
""" if two_tasks else ""

    agent_extra = """
class A2:
    agent_id = \"a2\"
    async def run(self, state, context, tools=None):
        state.output = {
            \"message\": {\"role\": \"assistant\", \"content\": \"ok\"},
            \"usage\": {\"input_tokens\": 1, \"output_tokens\": 1, \"total_tokens\": 2},
            \"trace_events\": [{\"event\": \"run\"}],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent2 = A2()
""" if two_agents else ""

    (tmp_path / "task.py").write_text(
        f"""
from snowl.core import EnvSpec, Task

task1 = Task(
    task_id=\"t1\",
    env_spec=EnvSpec(env_type=\"local\"),
    sample_iter_factory=lambda: iter([{{\"id\": \"s1\", \"input\": \"x\"}}]),
)
{task_extra}
""",
        encoding="utf-8",
    )

    (tmp_path / "agent.py").write_text(
        f"""
from snowl.core import StopReason

class A1:
    agent_id = \"a1\"
    async def run(self, state, context, tools=None):
        state.output = {{
            \"message\": {{\"role\": \"assistant\", \"content\": \"ok\"}},
            \"usage\": {{\"input_tokens\": 1, \"output_tokens\": 1, \"total_tokens\": 2}},
            \"trace_events\": [{{\"event\": \"run\"}}],
        }}
        state.stop_reason = StopReason.COMPLETED
        return state

agent1 = A1()
{agent_extra}
""",
        encoding="utf-8",
    )

    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score

class S:
    scorer_id = "s"
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}

scorer = S()
""",
        encoding="utf-8",
    )


def test_plan_mode_single_and_artifacts_written(tmp_path: Path) -> None:
    _write_project(tmp_path, two_tasks=False, two_agents=False)
    result = asyncio.run(run_eval(tmp_path))

    assert result.plan.mode == "single"
    assert result.summary.total == 1
    artifacts = Path(result.artifacts_dir)
    assert (artifacts / "plan.json").exists()
    assert (artifacts / "summary.json").exists()
    assert (artifacts / "outcomes.json").exists()

    summary = json.loads((artifacts / "summary.json").read_text(encoding="utf-8"))
    assert summary["success"] == 1
    assert result.rerun_command.startswith("snowl eval")


def test_plan_mode_matrix_and_filters(tmp_path: Path) -> None:
    _write_project(tmp_path, two_tasks=True, two_agents=True)

    full = asyncio.run(run_eval(tmp_path))
    assert full.plan.mode == "matrix"
    assert len(full.outcomes) == 4

    filtered = asyncio.run(run_eval(tmp_path, task_filter=["t2"], agent_filter=["a1"]))
    assert filtered.plan.mode == "single"
    assert len(filtered.outcomes) == 1
    assert filtered.plan.task_ids == ["t2"]
    assert filtered.plan.agent_ids == ["a1"]
