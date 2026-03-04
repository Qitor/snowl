from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.eval import run_eval
from snowl.ui import InteractionController


def test_command_palette_and_keyboard_navigation_state() -> None:
    c = InteractionController()
    assert c.handle_input("/task t1,t2") == "task_filter=t1,t2"
    assert c.handle_input("/agent a1") == "agent_filter=a1"
    assert c.handle_input("/variant v1") == "variant_filter=v1"
    assert c.handle_input("/status error,incorrect") == "status_filter=error,incorrect"
    assert c.handle_input("/focus t2") == "focus_task_id=t2"
    assert c.handle_input("tab").startswith("focused_panel_index=")
    assert c.handle_input("j").startswith("selected_task_index=")
    assert c.handle_input("enter").startswith("focus_locked=")
    assert c.handle_input("/rerun failed") == "rerun_failed_requested=true"
    assert c.handle_input("/theme quiet") == "theme_mode=quiet"
    assert c.handle_input("/banner hide") == "banner_collapsed=True"
    assert c.handle_input("/mode qa_dense") == "panel_mode=qa_dense"
    assert c.handle_input("/mode compare_dense") == "panel_mode=compare_dense"
    assert c.handle_input("/qa expand") == "qa_result_expanded=True"
    assert c.handle_input("/help").startswith("show_help=")
    assert c.handle_input("/statu error").startswith("unknown_command=statu nearest=/status")
    flags = c.to_cli_flags()
    assert "--task" in flags
    assert "--agent" in flags
    assert "--variant" in flags
    assert "--rerun-failed-only" in flags


def test_command_buffer_editing_state() -> None:
    c = InteractionController()
    c.command_start("/")
    c.command_append("task t1")
    assert c.command_mode is True
    assert c.command_buffer == "/task t1"
    c.command_backspace()
    assert c.command_buffer == "/task t"
    token = c.command_submit()
    assert token == "/task t"
    assert c.command_mode is False
    assert c.command_buffer == ""


def test_command_history_and_completion() -> None:
    c = InteractionController()
    c.command_start("/")
    c.command_append("sta")
    assert c.command_complete() == "/status"
    assert "/status" in c.command_suggestions
    c.command_append(" error")
    assert c.command_submit() == "/status error"

    c.command_start("/")
    c.command_append("task t1")
    assert c.command_submit() == "/task t1"

    c.command_start("/")
    assert c.command_history_prev() == "/task t1"
    assert c.command_history_prev() == "/status error"
    assert c.command_history_next() == "/task t1"
    assert c.command_history_next() == "/"


def test_slash_command_parity_and_interaction_log_written(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
t1 = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
t2 = Task(task_id="t2", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s2","input":"y"}]))
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

    ctl = InteractionController()
    ctl.queued_inputs = ["/task t1", "/agent a1", "/variant default", "/rerun failed"]
    interactive = asyncio.run(run_eval(tmp_path, renderer=None, interaction_controller=ctl))
    scripted = asyncio.run(run_eval(tmp_path, renderer=None, task_filter=["t1"], agent_filter=["a1"], variant_filter=["default"]))

    assert interactive.summary.total == scripted.summary.total == 1
    profiling = json.loads((Path(interactive.artifacts_dir) / "profiling.json").read_text(encoding="utf-8"))
    assert profiling["interaction"]["actions"]
    assert "--task t1" in profiling["interaction"]["equivalent_cli"]
    assert "--agent a1" in profiling["interaction"]["equivalent_cli"]
    assert "--variant default" in profiling["interaction"]["equivalent_cli"]
