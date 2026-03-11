from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from snowl.eval import _derive_pretask_events, run_eval


def _write_project(tmp_path: Path) -> None:
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
        return {"accuracy": Score(value=1.0)}

scorer = S()
""",
        encoding="utf-8",
    )


def test_eval_manifest_and_events_include_experiment_and_event_id(tmp_path: Path) -> None:
    _write_project(tmp_path)
    result = asyncio.run(run_eval(tmp_path, renderer=None, experiment_id="exp-demo"))
    out_dir = Path(result.artifacts_dir)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "exp-demo"
    assert manifest["event_stream_mode"] == "live_append"

    lines = [json.loads(x) for x in (out_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert lines
    assert all("event_id" in row for row in lines)
    assert all("experiment_id" in row for row in lines)
    assert all("seq" in row for row in lines)
    assert {row["experiment_id"] for row in lines} == {"exp-demo"}

    indexes = [int(row["event_index"]) for row in lines]
    seqs = [int(row["seq"]) for row in lines]
    assert indexes == sorted(indexes)
    assert indexes[0] == 1
    assert seqs == indexes


def test_eval_writes_live_metadata_before_trials_start(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(
    task_id="strongreject:test",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]),
    metadata={"benchmark": "strongreject"},
)
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason, make_agent_variant

class A:
    def __init__(self, content: str) -> None:
        self.agent_id = "chatagent"
        self._content = content

    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content": self._content},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agents = [
    make_agent_variant(agent=A("v1"), agent_id="chatagent", variant_id="qwen25_7b", model="Qwen/Qwen2.5-7B-Instruct"),
    make_agent_variant(agent=A("v2"), agent_id="chatagent", variant_id="qwen3_32b", model="Qwen/Qwen3-32B"),
]
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
        return {"strongreject": Score(value=1.0)}

scorer = S()
""",
        encoding="utf-8",
    )

    observed: dict[str, object] = {}

    def _on_bootstrap(meta) -> None:
        out_dir = Path(meta.artifacts_dir)
        observed["manifest"] = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        observed["plan"] = json.loads((out_dir / "plan.json").read_text(encoding="utf-8"))
        observed["profiling"] = json.loads((out_dir / "profiling.json").read_text(encoding="utf-8"))

    result = asyncio.run(run_eval(tmp_path, renderer=None, experiment_id="exp-live", on_run_bootstrap=_on_bootstrap))
    assert result.summary.total == 2

    manifest = observed["manifest"]
    plan = observed["plan"]
    profiling = observed["profiling"]
    assert isinstance(manifest, dict)
    assert isinstance(plan, dict)
    assert isinstance(profiling, dict)
    assert manifest["benchmark"] == "strongreject"
    assert manifest["status"] == "running"
    assert plan["trial_count"] == 2
    assert plan["variant_ids"] == ["qwen25_7b", "qwen3_32b"]
    assert profiling["run"]["benchmark"] == "strongreject"
    assert profiling["throughput"]["trial_count"] == 2
    task_rows = profiling["task_monitor"]
    assert len(task_rows) == 2
    assert {row["variant_id"] for row in task_rows} == {"qwen25_7b", "qwen3_32b"}
    assert {row["model"] for row in task_rows} == {"Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen3-32B"}
    assert {row["status"] for row in task_rows} == {"queued"}


def test_pretask_event_normalization_from_container_and_command_events() -> None:
    build_evt = {"event": "terminalbench.container.build", "exit_code": 1}
    rows = _derive_pretask_events(build_evt)
    assert rows and rows[0]["event"] == "pretask.build"
    assert rows[0]["status"] == "failed"

    start_evt = {
        "event": "runtime.env.command.finish",
        "command_text": "docker compose -p p1 -f c.yml up -d",
        "exit_code": 0,
    }
    rows2 = _derive_pretask_events(start_evt)
    assert rows2 and rows2[0]["event"] == "pretask.start"
    assert rows2[0]["status"] == "success"

    ready_evt = {"event": "osworld.container.visual_ready", "ready": True}
    rows3 = _derive_pretask_events(ready_evt)
    assert rows3 and rows3[0]["event"] == "pretask.ready"
    assert rows3[0]["status"] == "success"


def test_eval_writes_runtime_state_for_completed_run(tmp_path: Path) -> None:
    _write_project(tmp_path)
    result = asyncio.run(run_eval(tmp_path, renderer=None, experiment_id="exp-runtime-state"))
    out_dir = Path(result.artifacts_dir)

    runtime_state = json.loads((out_dir / "runtime_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert runtime_state["status"] == "completed"
    assert runtime_state["termination_reason"] == "completed"
    assert runtime_state["owner_pid"] > 0
    assert runtime_state["heartbeat_ts_ms"] >= runtime_state["started_ts_ms"]
    assert runtime_state["ended_ts_ms"] >= runtime_state["started_ts_ms"]
    assert manifest["status"] == "completed"
    assert manifest["runtime_state"] == "runtime_state.json"


def test_eval_marks_runtime_state_cancelled_on_task_cancellation(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
import asyncio
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        await asyncio.sleep(1.0)
        state.output = {
            "message": {"role":"assistant", "content":"late"},
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
        return {"accuracy": Score(value=1.0)}

scorer = S()
""",
        encoding="utf-8",
    )

    observed: dict[str, Path] = {}

    async def _run_and_cancel() -> None:
        def _on_bootstrap(meta) -> None:
            observed["artifacts_dir"] = Path(meta.artifacts_dir)

        task = asyncio.create_task(run_eval(tmp_path, renderer=None, on_run_bootstrap=_on_bootstrap))
        while "artifacts_dir" not in observed:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run_and_cancel())

    runtime_state = json.loads((observed["artifacts_dir"] / "runtime_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((observed["artifacts_dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert runtime_state["status"] == "cancelled"
    assert runtime_state["termination_reason"] == "cancelled"
    assert runtime_state["ended_ts_ms"] >= runtime_state["started_ts_ms"]
    assert manifest["status"] == "cancelled"


def test_web_monitor_classifies_cancelled_zombie_and_observer_stale(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node is required for Next monitor status classification test")
    repo_root = Path(__file__).resolve().parents[1]

    now_ms = int(time.time() * 1000)
    runs_root = tmp_path / ".snowl" / "runs"
    by_run_id = runs_root / "by_run_id"
    by_run_id.mkdir(parents=True, exist_ok=True)

    def _mk_run(run_id: str, *, runtime_status: str, heartbeat_ts_ms: int, last_event_ts_ms: int, owner_pid: int) -> Path:
        run_dir = runs_root / run_id.replace("run-", "")
        run_dir.mkdir(parents=True, exist_ok=True)
        (by_run_id / run_id).write_text(str(run_dir), encoding="utf-8")
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")
        (run_dir / "profiling.json").write_text(json.dumps({"run": {"run_id": run_id, "benchmark": "strongreject"}}), encoding="utf-8")
        (run_dir / "plan.json").write_text(json.dumps({"trial_count": 2, "task_ids": ["strongreject:test"], "agent_ids": ["chatagent"], "variant_ids": ["qwen25_7b"]}), encoding="utf-8")
        (run_dir / "manifest.json").write_text(
            json.dumps({"run_id": run_id, "experiment_id": run_id, "benchmark": "strongreject", "status": "running"}),
            encoding="utf-8",
        )
        (run_dir / "runtime_state.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "experiment_id": run_id,
                    "benchmark": "strongreject",
                    "status": runtime_status,
                    "owner_pid": owner_pid,
                    "started_ts_ms": now_ms - 1000,
                    "heartbeat_ts_ms": heartbeat_ts_ms,
                    "last_event_ts_ms": last_event_ts_ms,
                    "last_progress_ts_ms": last_event_ts_ms,
                }
            ),
            encoding="utf-8",
        )
        stale_sec = (now_ms - last_event_ts_ms) / 1000.0
        os.utime(run_dir / "events.jsonl", (time.time() - stale_sec, time.time() - stale_sec))
        os.utime(run_dir / "profiling.json", (time.time() - stale_sec, time.time() - stale_sec))
        return run_dir

    _mk_run(
        "run-cancelled-demo",
        runtime_status="cancelled",
        heartbeat_ts_ms=now_ms - 1_000,
        last_event_ts_ms=now_ms - 1_000,
        owner_pid=999999,
    )
    _mk_run(
        "run-zombie-demo",
        runtime_status="running",
        heartbeat_ts_ms=now_ms - 180_000,
        last_event_ts_ms=now_ms - 180_000,
        owner_pid=999999,
    )
    _mk_run(
        "run-observer-stale-demo",
        runtime_status="running",
        heartbeat_ts_ms=now_ms,
        last_event_ts_ms=now_ms - 60_000,
        owner_pid=999999,
    )

    script = f"""
import {{ RunMonitorStore }} from {json.dumps(str(repo_root / 'webui' / 'src' / 'server' / 'monitor.ts'))};
const store = new RunMonitorStore({{ projectDir: {json.dumps(str(tmp_path))} }});
try {{
  const rows = store.listRuns();
  console.log(JSON.stringify(rows));
}} finally {{
  store.stop();
}}
"""
    completed = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    rows = json.loads(completed.stdout)
    keyed = {row["run_id"]: row for row in rows}
    assert keyed["run-cancelled-demo"]["status"] == "cancelled"
    assert keyed["run-zombie-demo"]["status"] == "zombie"
    assert keyed["run-observer-stale-demo"]["status"] == "running"
    assert keyed["run-observer-stale-demo"]["observer_stale"] is True


def test_web_monitor_prefers_runtime_running_over_stale_summary(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node is required for Next monitor status classification test")
    repo_root = Path(__file__).resolve().parents[1]

    now_ms = int(time.time() * 1000)
    run_id = "run-retry-active"
    runs_root = tmp_path / ".snowl" / "runs"
    by_run_id = runs_root / "by_run_id"
    by_run_id.mkdir(parents=True, exist_ok=True)
    run_dir = runs_root / "retry-active"
    run_dir.mkdir(parents=True, exist_ok=True)
    (by_run_id / run_id).write_text(str(run_dir), encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    (run_dir / "aggregate.json").write_text(json.dumps({"matrix": {}, "by_task_agent": {}}), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"total": 1, "success": 0, "incorrect": 0, "error": 1, "limit_exceeded": 0, "cancelled": 0}), encoding="utf-8")
    (run_dir / "profiling.json").write_text(json.dumps({"run": {"run_id": run_id, "benchmark": "strongreject"}}), encoding="utf-8")
    (run_dir / "plan.json").write_text(json.dumps({"trial_count": 1, "task_ids": ["strongreject:test"], "agent_ids": ["chatagent"], "variant_ids": ["qwen25_7b"]}), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "experiment_id": run_id, "benchmark": "strongreject", "status": "running"}),
        encoding="utf-8",
    )
    (run_dir / "runtime_state.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "experiment_id": run_id,
                "benchmark": "strongreject",
                "status": "running",
                "owner_pid": os.getpid(),
                "started_ts_ms": now_ms - 5_000,
                "heartbeat_ts_ms": now_ms,
                "last_event_ts_ms": now_ms,
                "last_progress_ts_ms": now_ms,
            }
        ),
        encoding="utf-8",
    )

    script = f"""
import {{ RunMonitorStore }} from {json.dumps(str(repo_root / 'webui' / 'src' / 'server' / 'monitor.ts'))};
const store = new RunMonitorStore({{ projectDir: {json.dumps(str(tmp_path))} }});
try {{
  const rows = store.listRuns();
  console.log(JSON.stringify(rows));
}} finally {{
  store.stop();
}}
"""
    completed = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    rows = json.loads(completed.stdout)
    keyed = {row["run_id"]: row for row in rows}
    assert keyed[run_id]["status"] == "running"
    assert keyed[run_id]["runner_alive"] is True
