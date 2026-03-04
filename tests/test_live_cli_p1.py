from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from snowl.eval import run_eval
from snowl.ui import InteractionController, LiveConsoleRenderer


@dataclass(frozen=True)
class _Plan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    variant_ids: list[str]
    sample_count: int
    trials: list[str]


@dataclass(frozen=True)
class _Trial:
    task_id: str
    agent_id: str
    variant_id: str
    sample_id: str


class _Status:
    def __init__(self, value: str) -> None:
        self.value = value


class _Usage:
    total_tokens = 10


class _TaskResult:
    def __init__(self, status: str) -> None:
        self.task_id = "t1"
        self.agent_id = "a1"
        self.sample_id = "s1"
        self.status = _Status(status)
        self.usage = _Usage()
        self.payload = {"variant_id": "v1", "model": "m1"}
        self.error = None


class _Outcome:
    def __init__(self, status: str) -> None:
        self.task_result = _TaskResult(status)
        self.trace = {"trace_events": [{"event": "agent.run"}]}
        self.scores = {}


class _Aggregate:
    by_task_agent = {
        "t1::a1::v1": {
            "task_id": "t1",
            "agent_id": "a1",
            "variant_id": "v1",
            "model": "m1",
            "status_counts": {"success": 1},
            "metrics": {"accuracy": 1.0},
        }
    }
    matrix = {"t1": {"a1#v1": {"accuracy": 1.0}}}


@dataclass(frozen=True)
class _Summary:
    total: int
    success: int
    incorrect: int
    error: int
    limit_exceeded: int
    cancelled: int


def test_live_renderer_multi_panel_snapshot_contains_required_sections() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(_Plan("agent_compare", ["t1"], ["a1"], ["v1"], 1, ["x"]))
        renderer.render_controls()
        renderer.render_trial_start(_Trial("t1", "a1", "v1", "s1"), 1, 1)
        renderer.render_runtime_event({"event": "terminalbench.container.starting", "project": "p1"})
        renderer.render_compare(_Aggregate())
        renderer.render_trial_finish(_Outcome("error"))
        renderer.render_global(done=1, total=1, success=0, incorrect=0, other=1)
        renderer.render_summary(_Summary(1, 0, 0, 1, 0, 0), "/tmp/run", "snowl eval .")

    out = buf.getvalue()
    assert ("SNOWL" in out) or ("minimalist stream runtime" in out)
    assert ("Agent Evaluation Command Center" in out) or ("minimalist stream runtime" in out)
    assert "TASK QUEUE" in out
    assert "TASK DETAIL" in out
    assert "EVENT STREAM" in out
    assert any("terminalbench.container.starting" in row for row in renderer._events)
    assert any("project=p1" in row for row in renderer._events)


def test_live_renderer_includes_docker_command_payload_details() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())

    renderer.render_runtime_event(
        {
            "event": "terminalbench.command.exec",
            "task_id": "terminalbench:test",
            "agent_id": "a1",
            "payload": {
                "command_text": "docker compose up -d",
                "exit_code": 1,
                "duration_ms": 2540,
                "stdout_tail": "pulling layers",
                "stderr_tail": "permission denied /var/run/docker.sock",
            },
        }
    )
    line = renderer._events[-1]
    assert "terminalbench.command.exec" in line
    assert "command_text=docker compose up -d" in line
    assert "exit_code=1" in line
    assert "duration_ms=2540" in line
    assert "stdout_tail=pulling layers" in line
    assert "stderr_tail=permission denied /var/run/docker.sock" in line


def test_env_timeline_captures_env_phase_docker_events() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())
    renderer.render_runtime_event(
        {
            "event": "terminalbench.container.stopped",
            "task_id": "terminalbench:test",
            "agent_id": "a1",
            "payload": {
                "command_text": "docker compose -p p1 down",
                "stderr_tail": "connect: operation not permitted /Users/morinop/.docker/run/docker.sock",
            },
        }
    )
    rows = renderer._render_panel_env_timeline(renderer._get_spec("env_timeline"), "text")
    joined = "\n".join(rows)
    assert "terminalbench.container.stopped" in joined
    assert "docker.sock" in joined


def test_interaction_filters_match_no_ui_cli_parity(tmp_path: Path) -> None:
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
    ctl.queued_inputs = ["task=t1"]
    interactive = asyncio.run(run_eval(tmp_path, renderer=None, interaction_controller=ctl))
    scripted = asyncio.run(run_eval(tmp_path, renderer=None, task_filter=["t1"]))

    assert interactive.summary.total == scripted.summary.total == 1
    assert {o.task_result.task_id for o in interactive.outcomes} == {"t1"}
    profiling = json.loads((Path(interactive.artifacts_dir) / "profiling.json").read_text(encoding="utf-8"))
    assert "--task t1" in profiling["interaction"]["equivalent_cli"]


def test_live_renderer_buffers_are_bounded_under_event_burst() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, max_events=12, refresh_interval_ms=1000)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    for i in range(80):
        renderer.render_runtime_event({"event": "runtime.tick", "idx": i})
    assert len(renderer._events) <= 12
    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_summary(_Summary(0, 0, 0, 0, 0, 0), "/tmp/r", "snowl eval .")
    assert any("ui.throttle suppressed=" in row for row in renderer._events)


def test_live_renderer_emits_ui_throttle_config_and_banner_modes() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=100, refresh_interval_ms=120, max_events=33, max_failures=22, max_active_trials=11)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    controller = InteractionController()
    controller.banner_collapsed = True
    controller.theme_mode = "quiet"
    renderer.bind_controller(controller)

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(_Plan("single", ["t1"], ["a1"], ["v1"], 1, ["x"]))
    out = buf.getvalue()

    assert "Snowl Live" in out
    assert renderer._active_theme_mode() == "quiet"
    assert any(
        "ui.throttle refresh_interval_ms=120 max_events=33 max_failures=22 max_active_trials=11" in row
        for row in renderer._events
    )


def test_live_renderer_footer_shows_command_buffer() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    ctl = InteractionController()
    ctl.command_start("/")
    ctl.command_append("task t1")
    renderer.bind_controller(ctl)

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(_Plan("single", ["t1"], ["a1"], ["v1"], 1, ["x"]))
    out = buf.getvalue()
    assert "command> /task t1" in out


def test_qa_result_falls_back_to_latest_scored_context_when_selected_has_no_result() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer.bind_controller(InteractionController())
    renderer._trial_context = {
        "k-empty": {"input": "q"},
        "k-scored": {"output_content": "answer", "final_score": 1.0, "score_lines": ["strongreject=1.000"]},
    }
    rows = renderer._render_panel_qa_result(renderer._get_spec("qa_result"), "text")
    assert any("output:" in r for r in rows)
    assert any("verdict=PASS" in r for r in rows)


def test_research_theme_banner_rows_are_colored_and_tagged() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0, theme_mode="research")
    renderer.bind_controller(InteractionController(theme_mode="research"))
    tokens = renderer._theme_tokens()
    rows = renderer._render_banner_rich_rows(120, tokens)
    text = "\n".join(getattr(r, "plain", str(r)) for r in rows)
    assert "minimalist stream runtime" in text
    assert "theme=research" in text


def test_strongreject_auto_uses_qa_dense_panels_and_no_loading_placeholder() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    ctl = InteractionController()
    renderer.bind_controller(ctl)
    renderer._benchmark_name = "strongreject"

    trial = _Trial("strongreject:t1", "a1", "v1", "s1")
    plan = _Plan("single", ["strongreject:t1"], ["a1"], ["v1"], 1, [trial])
    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
    out0 = buf.getvalue()

    outc = _Outcome("success")
    outc.task_result.task_id = "strongreject:t1"
    outc.task_result.agent_id = "a1"
    outc.task_result.sample_id = "s1"
    outc.task_result.payload = {"variant_id": "v1"}
    outc.task_result.final_output = {"content": "model answer text"}

    class _Score:
        def __init__(self) -> None:
            self.value = 0.8
            self.explanation = "acceptable"
            self.metadata = {"judge_parsed": {"verdict": "allow", "score": 0.8}}

    outc.scores = {"strongreject": _Score()}
    renderer.render_trial_finish(outc)

    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        renderer.render_global(done=1, total=1, success=1, incorrect=0, other=0)
    out = out0 + buf2.getvalue()
    assert "TASK DETAIL" in out
    assert ("QA RESULT" in out) or ("STAGE" in out)
    assert "loading..." not in out


def test_live_activity_shows_querying_model_state() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())
    renderer._benchmark_name = "strongreject"

    trial = _Trial("strongreject:t1", "a1", "v1", "s1")
    plan = _Plan("single", ["strongreject:t1"], ["a1"], ["v1"], 1, [trial])

    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
        renderer.render_runtime_event(
            {
                "event": "runtime.model.query.start",
                "task_id": "strongreject:t1",
                "agent_id": "a1",
                "variant_id": "v1",
                "sample_id": "s1",
            }
        )
    assert renderer._inflight_model_queries == 1
    assert renderer._activity_label == "querying-model"


def test_stage_widget_panel_renders_in_rich_layout() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())
    renderer._benchmark_name = "strongreject"
    plan = _Plan("single", ["strongreject:t1"], ["a1"], ["v1"], 1, [_Trial("strongreject:t1", "a1", "v1", "s1")])
    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(plan)
    out = buf.getvalue()
    assert "STAGE" in out
    assert "METRIC SPOTLIGHT" in out


def test_overview_shows_scorer_metrics_summary() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer._now = lambda: "12:00:00"  # type: ignore[method-assign]
    renderer.bind_controller(InteractionController())

    trial = _Trial("t1", "a1", "v1", "s1")
    plan = _Plan("single", ["t1"], ["a1"], ["v1"], 1, [trial])
    renderer.render_plan(plan)

    outc = _Outcome("success")
    outc.task_result.task_id = "t1"
    outc.task_result.agent_id = "a1"
    outc.task_result.sample_id = "s1"
    outc.task_result.payload = {"variant_id": "v1"}

    class _Score:
        def __init__(self, v: float) -> None:
            self.value = v
            self.explanation = ""
            self.metadata = {}

    outc.scores = {"strongreject": _Score(0.2), "safety": _Score(1.0)}
    renderer.render_trial_finish(outc)

    renderer.render_global(done=1, total=1, success=1, incorrect=0, other=0)
    metrics_text = renderer._metrics_overview_text(limit=3)
    assert "metrics:" in metrics_text
    assert "strongreject=avg:0.200" in metrics_text
    assert "safety=avg:1.000" in metrics_text


def test_metric_spotlight_and_compare_board_use_same_primary_metric(tmp_path: Path) -> None:
    (tmp_path / "panels.yml").write_text(
        """
panels:
  - type: metric_spotlight
    title: METRIC SPOTLIGHT
    source: metrics
    options:
      primary_metric: safety
      top_k: 2
  - type: compare_board
    title: COMPARE BOARD
    source: compare
layout:
  left: [task_queue]
  right: [metric_spotlight, compare_board]
""",
        encoding="utf-8",
    )
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0)
    renderer.configure_panels(benchmark_name="strongreject", project_dir=tmp_path)
    renderer._benchmark_name = "strongreject"

    class _Agg:
        by_task_agent = {
            "t1::a1::v1": {
                "task_id": "t1",
                "agent_id": "a1",
                "variant_id": "v1",
                "model": "m1",
                "status_counts": {"success": 1},
                "metrics": {"safety": 0.9, "accuracy": 0.4},
            },
            "t1::a2::v1": {
                "task_id": "t1",
                "agent_id": "a2",
                "variant_id": "v1",
                "model": "m2",
                "status_counts": {"success": 1},
                "metrics": {"safety": 0.6, "accuracy": 0.8},
            },
        }
        matrix = {"t1": {"a1#v1": {"safety": 0.9}, "a2#v1": {"safety": 0.6}}}

    renderer.render_compare(_Agg())
    assert renderer._compare_focus_metric == "safety"
    assert renderer._compare_rows
    assert "focus=safety" in renderer._compare_rows[0]
    spotlight_spec = renderer._get_spec("metric_spotlight")
    spotlight_rows = renderer._render_panel_metric_spotlight(spotlight_spec, "text")
    assert any("leaderboard(safety)" in row for row in spotlight_rows)


def test_compare_dense_groups_compare_board_by_variant() -> None:
    renderer = LiveConsoleRenderer(verbose=True, width=120, refresh_interval_ms=0, ui_mode="compare_dense")
    renderer.bind_controller(InteractionController(panel_mode="compare_dense"))

    class _Agg:
        by_task_agent = {
            "t1::a1::v1": {
                "task_id": "t1",
                "agent_id": "a1",
                "variant_id": "v1",
                "model": "m1",
                "status_counts": {"success": 1},
                "metrics": {"strongreject": 0.8},
            },
            "t1::a2::v2": {
                "task_id": "t1",
                "agent_id": "a2",
                "variant_id": "v2",
                "model": "m2",
                "status_counts": {"error": 1},
                "metrics": {"strongreject": 0.6},
            },
        }

    renderer.render_compare(_Agg())
    spec = renderer._get_spec("compare_board")
    rows = renderer._render_panel_compare_board(spec, "text")
    assert rows[0].startswith("focus_metric=")
    assert any("variant=v1" in row for row in rows)
    assert any("variant=v2" in row for row in rows)
    assert any("rank=1" in row for row in rows)
