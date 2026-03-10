from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from snowl.eval import run_eval
from scripts.throughput_baseline import run_baseline
from scripts.runtime_scheduler_benchmark import run_benchmark as run_scheduler_benchmark
from snowl.envs.sandbox_runtime import BoundedSandboxRuntime


def _write_project(
    tmp_path: Path,
    *,
    sample_count: int = 2,
    sleep_sec: float = 0.0,
    scorer_sleep_sec: float = 0.0,
) -> None:
    sample_lines = "\n".join(
        [f'    yield {{"id": "s{i}", "input": "x{i}"}}' for i in range(sample_count)]
    )
    (tmp_path / "task.py").write_text(
        f"""
from snowl.core import EnvSpec, Task

def _samples():
{sample_lines}

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=_samples)
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        f"""
import asyncio
from snowl.core import StopReason
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        await asyncio.sleep({sleep_sec})
        state.output = {{
            "message": {{"role":"assistant", "content":"ok"}},
            "usage": {{"input_tokens":1, "output_tokens":1, "total_tokens":2}},
            "trace_events": [],
        }}
        state.stop_reason = StopReason.COMPLETED
        return state
agent = A()
""",
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        f"""
import time
from snowl.core import Score
class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        _ = (task_result, trace, context)
        time.sleep({scorer_sleep_sec})
        return {{"accuracy": Score(value=1.0)}}
scorer = S()
""",
        encoding="utf-8",
    )


def test_runtime_controls_written_to_checkpoint_and_profiling(tmp_path: Path) -> None:
    _write_project(tmp_path, sample_count=2)
    result = asyncio.run(
        run_eval(
            tmp_path,
            renderer=None,
            resume=True,
            checkpoint_key="k1",
            max_running_trials=2,
            max_container_slots=1,
            max_builds=1,
            provider_budgets={"default": 1},
        )
    )
    out_dir = Path(result.artifacts_dir)
    profiling = json.loads((out_dir / "profiling.json").read_text(encoding="utf-8"))
    assert profiling["controls"]["max_running_trials"] == 2
    assert profiling["controls"]["max_container_slots"] == 1
    assert profiling["throughput"]["trial_count"] == 2

    checkpoint = json.loads(
        (tmp_path / ".snowl" / "checkpoints" / "k1.json").read_text(encoding="utf-8")
    )
    assert checkpoint["in_progress"] == {}
    assert checkpoint["meta"]["controls"]["provider_budgets"] == {"default": 1}


def test_max_trials_improves_wallclock_for_sleepy_agent(tmp_path: Path) -> None:
    _write_project(tmp_path, sample_count=4, sleep_sec=0.05)
    t1 = time.perf_counter()
    asyncio.run(run_eval(tmp_path, renderer=None, max_running_trials=1))
    seq = time.perf_counter() - t1

    t2 = time.perf_counter()
    asyncio.run(run_eval(tmp_path, renderer=None, max_running_trials=2))
    par = time.perf_counter() - t2
    assert par < seq


def test_decoupled_scoring_improves_wallclock_vs_serial_baseline(tmp_path: Path) -> None:
    _write_project(tmp_path, sample_count=4, sleep_sec=0.05, scorer_sleep_sec=0.05)

    started = time.perf_counter()
    asyncio.run(
        run_eval(
            tmp_path,
            renderer=None,
            max_running_trials=1,
            max_scoring_tasks=1,
            provider_budgets={"default": 1},
        )
    )
    overlapped = time.perf_counter() - started

    serial_baseline = 4 * (0.05 + 0.05)
    assert overlapped < serial_baseline * 0.9


def test_throughput_baseline_report_shape() -> None:
    root = Path(__file__).resolve().parents[1]
    report = run_baseline(root=root, split="test", limit=1)
    assert "terminalbench" in report
    assert "osworld" in report
    assert report["terminalbench"]["sample_count"] >= 1


def test_runtime_scheduler_benchmark_reports_speedup_shape() -> None:
    report = run_scheduler_benchmark(sample_count=4, agent_sleep_sec=0.02, scorer_sleep_sec=0.02)
    assert report["kind"] == "qa_synthetic"
    assert report["serial"]["trials"] == 4
    assert report["tuned"]["trials"] == 4
    assert report["speedup"] > 1.0


def test_docker_like_tasks_default_to_serial_when_max_running_trials_not_explicit(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path, sample_count=2, sleep_sec=0.0)
    task_file = tmp_path / "task.py"
    task_file.write_text(
        task_file.read_text(encoding="utf-8").replace('env_type="local"', 'env_type="terminal"'),
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None))
    profiling = json.loads((Path(result.artifacts_dir) / "profiling.json").read_text(encoding="utf-8"))
    assert profiling["controls"]["max_running_trials"] == 1


def test_docker_like_tasks_keep_explicit_max_running_trials(tmp_path: Path) -> None:
    _write_project(tmp_path, sample_count=2, sleep_sec=0.0)
    task_file = tmp_path / "task.py"
    task_file.write_text(
        task_file.read_text(encoding="utf-8").replace('env_type="local"', 'env_type="terminal"'),
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None, max_running_trials=3))
    profiling = json.loads((Path(result.artifacts_dir) / "profiling.json").read_text(encoding="utf-8"))
    assert profiling["controls"]["max_running_trials"] == 3


def test_non_sandbox_tasks_do_not_instantiate_shared_sandbox_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_project(tmp_path, sample_count=1, sleep_sec=0.0)
    calls = {"count": 0}
    original_init = BoundedSandboxRuntime.__init__

    def _spy(self, inner, max_active):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return original_init(self, inner, max_active)

    monkeypatch.setattr(BoundedSandboxRuntime, "__init__", _spy)
    result = asyncio.run(run_eval(tmp_path, renderer=None))
    assert result.summary.total == 1
    assert calls["count"] == 0
