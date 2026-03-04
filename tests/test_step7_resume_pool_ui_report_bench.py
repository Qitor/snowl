from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from snowl.bench import check_benchmark_conformance, list_benchmarks
from snowl.cli import main
from snowl.core import EnvSpec, SandboxSpec, Score, ScoreContext, Task, TaskResult
from snowl.envs import WarmPoolSandboxRuntime
from snowl.eval import run_eval
from snowl.runtime import TrialRequest, execute_trial
from snowl.ui import InteractionController


class PassScorer:
    scorer_id = "pass"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=1.0)}


def test_warm_pool_reuse_across_trials() -> None:
    class Agent:
        agent_id = "a"

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            state.output = {
                "message": {"role": "assistant", "content": "ok"},
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "trace_events": [],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

    runtime = WarmPoolSandboxRuntime(max_pool_size=2)
    task = Task(
        task_id="t",
        env_spec=EnvSpec(
            env_type="docker",
            sandbox_spec=SandboxSpec(provider="docker", image="python:3.12"),
        ),
        sample_iter_factory=lambda: iter([]),
    )

    req = TrialRequest(task=task, agent=Agent(), scorer=PassScorer(), sample={"id": "s1", "input": "x"}, sandbox_runtime=runtime)

    async def _run() -> None:
        await execute_trial(req)
        await execute_trial(req)

    asyncio.run(_run())
    stats = runtime.stats()
    assert stats["prepared_new"] >= 1
    assert stats["reused"] >= 1


def test_resume_and_rerun_failed_only(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

def _samples():
    yield {"id": "s1", "input": "x"}

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=_samples)
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        # fail first, then succeed if marker exists
        state.output = {"message": {"role": "assistant", "content": "ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
        if context.sample_id == "s1":
            state.stop_reason = StopReason.ERROR
        else:
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
    scorer_id = "s"
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    # First run with checkpoint.
    r1 = asyncio.run(run_eval(tmp_path, renderer=None, resume=True, checkpoint_key="k1"))
    assert r1.summary.error >= 1

    # Rerun failed-only should be executable (even if still failing with current agent behavior).
    r2 = asyncio.run(run_eval(tmp_path, renderer=None, rerun_failed_only=True))
    assert r2.summary.total >= 1


def test_diagnostics_bundle_and_html_report_exist(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, SandboxSpec, Task

task = Task(
    task_id="t1",
    env_spec=EnvSpec(env_type="docker", sandbox_spec=SandboxSpec(provider="docker", image="python:3.12")),
    sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]),
)
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {"message": {"role": "assistant", "content": "ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
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
    scorer_id = "s"
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None))
    out = Path(result.artifacts_dir)
    assert (out / "report.html").exists()
    assert (out / "diagnostics_index.json").exists()


def test_interaction_controller_keys() -> None:
    c = InteractionController()
    assert c.handle_key("p") == "paused"
    assert c.paused is True
    assert c.handle_key("p") == "resumed"
    assert c.handle_key("f").startswith("only_failed_focus=")
    assert c.handle_key("a").startswith("group_by=")
    assert c.handle_key("t").startswith("group_by=")
    assert c.handle_key("r") == "rerun_failed_requested=true"
    assert c.handle_key("b").startswith("banner_collapsed=")
    assert c.handle_key("x").startswith("theme_mode=")
    assert c.handle_key("u").startswith("panel_mode=")
    assert c.handle_key("e").startswith("qa_result_expanded=")


def test_csv_adapter_registered_and_conformance(tmp_path: Path) -> None:
    names = {entry["name"] for entry in list_benchmarks()}
    assert "csv" in names

    csv_path = tmp_path / "bench.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "split", "input", "target"])
        writer.writeheader()
        writer.writerow({"id": "1", "split": "test", "input": "x", "target": "y"})

    report = check_benchmark_conformance("csv", benchmark_args=[f"dataset_path={csv_path}"])
    assert report["ok"] is True


def test_cli_eval_with_resume_flag(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {"message": {"role":"assistant", "content":"ok"}, "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2}, "trace_events": []}
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
    scorer_id = "s"
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    rc = main(["eval", str(tmp_path), "--resume", "--checkpoint-key", "t", "--no-ui"])
    assert rc == 0
