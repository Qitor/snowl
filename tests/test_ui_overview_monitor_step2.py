from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass

from snowl.ui import InteractionController, LiveConsoleRenderer


@dataclass(frozen=True)
class _Task:
    metadata: dict
    env_spec: object


@dataclass(frozen=True)
class _Trial:
    task_id: str
    agent_id: str
    variant_id: str
    sample_id: str
    sample: dict
    task: _Task


@dataclass(frozen=True)
class _Plan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    variant_ids: list[str]
    sample_count: int
    trials: list[_Trial]


def test_live_ui_overview_and_task_monitor_panels_render() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    controller = InteractionController()
    renderer.bind_controller(controller)

    trial = _Trial(
        task_id="strongreject:test",
        agent_id="chat",
        variant_id="default",
        sample_id="s1",
        sample={"id": "s1", "input": "forbidden prompt"},
        task=_Task(metadata={"benchmark": "strongreject"}, env_spec=object()),
    )
    plan = _Plan(
        mode="single",
        task_ids=["strongreject:test"],
        agent_ids=["chat"],
        variant_ids=["default"],
        sample_count=1,
        trials=[trial],
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
        renderer.render_trial_start(trial, 1, 1)
        renderer.render_runtime_event(
            {
                "event": "runtime.scorer.finish",
                "task_id": "strongreject:test",
                "agent_id": "chat",
                "variant_id": "default",
                "sample_id": "s1",
                "metrics": {"accuracy": 0.0},
                "message": "judge complete",
            }
        )

    out = buf.getvalue()
    assert "EVAL OVERVIEW" in out
    assert "TASK QUEUE" in out
    assert "TASK DETAIL" in out
    assert "strongreject" in out


def test_task_monitor_status_filter_and_focus_command() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    controller = InteractionController()
    controller.handle_input("status=error")
    controller.handle_input("focus=t2")
    renderer.bind_controller(controller)

    t1 = _Trial(
        task_id="t1",
        agent_id="a",
        variant_id="default",
        sample_id="s1",
        sample={"id": "s1", "input": "x"},
        task=_Task(metadata={"benchmark": "custom"}, env_spec=object()),
    )
    t2 = _Trial(
        task_id="t2",
        agent_id="a",
        variant_id="default",
        sample_id="s2",
        sample={"id": "s2", "input": "y"},
        task=_Task(metadata={"benchmark": "custom"}, env_spec=object()),
    )
    plan = _Plan(
        mode="task_sweep",
        task_ids=["t1", "t2"],
        agent_ids=["a"],
        variant_ids=["default"],
        sample_count=2,
        trials=[t1, t2],
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
        renderer.render_runtime_event(
            {"event": "runtime.trial.finish", "task_id": "t1", "agent_id": "a", "variant_id": "default", "sample_id": "s1", "status": "success"}
        )
        renderer.render_runtime_event(
            {"event": "runtime.trial.error", "task_id": "t2", "agent_id": "a", "variant_id": "default", "sample_id": "s2", "message": "boom"}
        )

    out = buf.getvalue()
    assert "status=error" in out
    states = renderer._task_monitor.list_states()
    assert any(s.task_id == "t2" and s.status.value == "error" for s in states)
