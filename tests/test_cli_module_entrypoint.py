from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_m_snowl_cli_invokes_main(tmp_path: Path) -> None:
    task = tmp_path / "task.py"
    agent = tmp_path / "agent.py"
    scorer = tmp_path / "scorer.py"
    task.write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
""",
        encoding="utf-8",
    )
    agent.write_text(
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
    scorer.write_text(
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

    proc = subprocess.run(
        [sys.executable, "-m", "snowl.cli", "eval", str(tmp_path), "--no-ui"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "Snowl Eval Summary:" in proc.stdout
    assert "log=" in proc.stdout
