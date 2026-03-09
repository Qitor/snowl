from __future__ import annotations

import asyncio
import json
from pathlib import Path

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
