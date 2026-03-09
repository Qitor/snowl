from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from snowl.cli import main


def test_cli_eval_auto_discovery(tmp_path: Path) -> None:
    (tmp_path / "tool.py").write_text(
        """
from snowl.core import tool

@tool
def echo(text: str) -> str:
    \"\"\"Echo.\"\"\"
    return text
        """,
        encoding="utf-8",
    )

    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

def _samples():
    yield {"id": "s1", "input": "hi"}

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=_samples)
        """,
        encoding="utf-8",
    )

    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a"
    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": "ok"},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [{"event": "run", "tool_names": [t.name for t in tools or []]}],
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
    scorer_id = "s"
    def score(self, task_result, trace, context):
        ok = "echo" in trace["trace_events"][0]["tool_names"]
        return {"accuracy": Score(value=1.0 if ok else 0.0)}

scorer = S()
        """,
        encoding="utf-8",
    )

    rc = main(["eval", str(tmp_path)])
    assert rc == 0


def test_cli_eval_accepts_ui_tuning_flags(tmp_path: Path) -> None:
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
        state.output = {"message":{"role":"assistant","content":"ok"}, "usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}, "trace_events":[]}
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
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )
    rc = main(
        [
            "eval",
            str(tmp_path),
            "--no-ui",
            "--ui-refresh-ms",
            "120",
            "--ui-max-events",
            "50",
            "--ui-max-failures",
            "40",
            "--ui-max-active-trials",
            "20",
            "--ui-refresh-profile",
            "low_cpu",
            "--ui-theme",
            "quiet",
            "--ui-mode",
            "compare_dense",
            "--ui-no-banner",
        ]
    )
    assert rc == 0


def test_cli_eval_keyboard_interrupt_prints_log_path(tmp_path: Path, monkeypatch, capsys) -> None:
    runs = tmp_path / ".snowl" / "runs" / "run-20260303T110000Z"
    runs.mkdir(parents=True)
    (runs / "run.log").write_text("partial\n", encoding="utf-8")

    def _raise_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "run", _raise_interrupt)
    rc = main(["eval", str(tmp_path), "--no-ui"])
    out = capsys.readouterr().out
    assert rc == 130
    assert "Interrupted by user." in out
    assert f"log={runs / 'run.log'}" in out


def test_close_renderer_calls_close_method() -> None:
    from snowl.cli import _close_renderer

    class _R:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    r = _R()
    _close_renderer(r)
    assert r.closed is True


def test_cli_eval_experiment_id_written_to_manifest(tmp_path: Path) -> None:
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
        state.output = {"message":{"role":"assistant","content":"ok"}, "usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}, "trace_events":[]}
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

    rc = main(["eval", str(tmp_path), "--no-ui", "--experiment-id", "exp-cli"])
    assert rc == 0

    runs_root = tmp_path / ".snowl" / "runs"
    run_dirs = sorted([p for p in runs_root.iterdir() if p.is_dir() and p.name != "by_run_id"])
    assert run_dirs
    manifest = json.loads((run_dirs[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "exp-cli"


def test_cli_web_monitor_missing_deps_returns_2(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    rc = main(["web", "monitor", "--project", str(tmp_path)])
    assert rc == 2
