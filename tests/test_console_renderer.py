from __future__ import annotations

from dataclasses import dataclass

from snowl.ui import ConsoleRenderer


@dataclass(frozen=True)
class _FakePlan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    sample_count: int
    trials: list[str]


@dataclass(frozen=True)
class _FakeSummary:
    total: int
    success: int
    incorrect: int
    error: int
    limit_exceeded: int
    cancelled: int


@dataclass(frozen=True)
class _FakeTrial:
    task_id: str
    agent_id: str
    sample_id: str | None


class _FakeStatus:
    value = "success"


class _FakeUsage:
    total_tokens = 3


class _FakeTaskResult:
    status = _FakeStatus()
    usage = _FakeUsage()
    error = None


class _FakeOutcome:
    task_result = _FakeTaskResult()
    trace = {"trace_events": [{"event": "agent.run"}]}


class _FakeError:
    code = "agent_runtime_error"
    message = "boom"


class _ErrStatus:
    value = "error"


class _ErrTaskResult:
    status = _ErrStatus()
    usage = _FakeUsage()
    error = _FakeError()


class _ErrOutcome:
    task_result = _ErrTaskResult()
    trace = {"trace_events": [{"event": "agent.run"}]}


def test_console_renderer_prints_global_trial_and_summary(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_plan(_FakePlan("single", ["t1"], ["a1"], 1, ["x"]))
    r.render_trial_start(_FakeTrial("t1", "a1", "s1"), 1, 1)
    r.render_trial_finish(_FakeOutcome())
    r.render_global(done=1, total=1, success=1, incorrect=0, other=0)
    r.render_summary(_FakeSummary(1, 1, 0, 0, 0, 0), "/tmp/out", "snowl eval .")

    out = capsys.readouterr().out
    # Rich Panel format — check for structural elements
    assert "Plan" in out
    assert "mode:" in out
    assert "tasks:" in out
    assert "Trial" in out
    assert "Progress" in out
    assert "Summary" in out
    assert "snowl eval ." in out
    assert "/tmp/out" in out


def test_console_renderer_prints_error_details(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_trial_finish(_ErrOutcome())
    out = capsys.readouterr().out
    assert "error" in out
    assert "agent_runtime_error" in out
    assert "boom" in out


def test_console_renderer_ignores_ui_heartbeat(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({"event": "ui.heartbeat"})
    r.render_runtime_event({"event": "runtime.trial.start", "task_id": "t1", "agent_id": "a1"})
    out = capsys.readouterr().out
    assert "ui.heartbeat" not in out
    # Generic events use [event_name] format with key: value
    assert "task_id: t1" in out
    assert "agent_id: a1" in out


def test_console_renderer_prints_model_io_input(capsys) -> None:
    r = ConsoleRenderer(verbose=True, width=1000)
    r.render_runtime_event(
        {
            "event": "runtime.model.io",
            "task_id": "t1",
            "agent_id": "a1",
            "model": "Qwen/Qwen3-32B",
            "base_url": "https://provider.example/v1",
            "provider_id": "siliconflow",
            "direction": "input",
            "message": "model input captured before provider call",
            "model_input": {
                "messages": [{"role": "user", "content": "hello"}],
                "generation_kwargs": {"temperature": 0.2},
            },
            "request": {
                "messages": [{"role": "user", "content": "hello"}],
                "generation_kwargs": {"temperature": 0.2},
            },
        }
    )
    out = capsys.readouterr().out
    assert "[model] input -> Qwen/Qwen3-32B" in out
    assert "messages: 1" in out


def test_console_renderer_prints_model_io_output(capsys) -> None:
    r = ConsoleRenderer(verbose=True, width=1000)
    r.render_runtime_event(
        {
            "event": "runtime.model.io",
            "task_id": "t1",
            "agent_id": "a1",
            "direction": "output",
            "model_output": {"role": "assistant", "content": "done"},
            "response": {
                "message": {"role": "assistant", "content": "done"},
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        }
    )
    out = capsys.readouterr().out
    assert "[model] output" in out
    assert "tokens:" in out


def test_console_renderer_format_agent_step(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({
        "event": "runtime.agent.step",
        "step": 3,
        "mode": "native_tools",
        "status": "running",
    })
    out = capsys.readouterr().out
    assert "Step 3" in out
    assert "native_tools" in out


def test_console_renderer_format_emulation(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({
        "event": "toolemu.emulation",
        "tool_name": "get_user_profile",
        "tool_args": {"user_id": "john_doe"},
        "observation": '{"status": "success", "profile": {"name": "John Doe"}}',
        "thought_summary": "Verified the tool call matches specification",
        "simulator_type": "std_thought",
        "scratchpad_entries": 3,
    })
    out = capsys.readouterr().out
    assert "[emulation] get_user_profile" in out
    assert "args:" in out
    assert "thought:" in out
    assert "observation:" in out
    assert "scratchpad: 3 entries" in out


def test_console_renderer_format_model_query(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({
        "event": "runtime.model.query.start",
        "model": "glm-5.1-w4a8",
    })
    r.render_runtime_event({
        "event": "runtime.model.query.finish",
        "model": "glm-5.1-w4a8",
        "duration_ms": 1234,
        "total_tokens": 200,
    })
    out = capsys.readouterr().out
    assert "querying glm-5.1-w4a8" in out
    assert "response <- glm-5.1-w4a8" in out
    assert "1234ms" in out


def test_console_renderer_format_scorer(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({
        "event": "runtime.scorer.start",
        "scorer_id": "toolemu_scorer",
    })
    r.render_runtime_event({
        "event": "runtime.scorer.finish",
        "metrics": {"toolemu_toolcall_risk": 1.0, "toolemu_helpfulness": 0.0},
    })
    out = capsys.readouterr().out
    assert "[scorer] scoring..." in out
    assert "[scorer] done" in out
    assert "toolemu_toolcall_risk: 1.000" in out


def test_console_renderer_prints_scorer_warning(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event(
        {
            "event": "runtime.scorer.warning",
            "scorer_id": "toolemu",
            "metric_name": "ToolCallRisk",
            "message": "Missing ToolEmu reference dependencies: references/PromptCoder",
            "failure_policy": "default_zero",
            "defaulted_metrics": ["ToolCallRisk"],
        }
    )
    out = capsys.readouterr().out
    assert "[scorer] warning ToolCallRisk" in out
    assert "Missing ToolEmu reference dependencies" in out
    assert "failure_policy: default_zero" in out


def test_console_renderer_format_model_error(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_runtime_event({
        "event": "runtime.model.query.error",
        "model": "glm-5.1-w4a8",
        "error_type": "TimeoutError",
        "message": "Connection timed out after 30s",
    })
    out = capsys.readouterr().out
    assert "[model] error" in out
    assert "TimeoutError" in out


def test_console_renderer_progress_bar(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_global(done=3, total=10, success=2, incorrect=1, other=0)
    out = capsys.readouterr().out
    assert "Progress" in out
    assert "3/10" in out


def test_console_renderer_compare_table(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    from types import SimpleNamespace
    aggregate = SimpleNamespace(matrix={
        "t1": {"a1": {"accuracy": 0.5, "f1": 0.6}, "a2": {"accuracy": 0.75, "f1": 0.8}},
    })
    r.render_compare(aggregate)
    out = capsys.readouterr().out
    assert "Compare" in out
    assert "accuracy" in out
    assert "0.500" in out or "0.75" in out


def test_console_renderer_no_truncation_on_long_lines(capsys) -> None:
    """Long lines should wrap, not truncate with >."""
    r = ConsoleRenderer(verbose=True, width=60)
    long_text = "x" * 200
    r._emit(long_text)
    out = capsys.readouterr().out
    assert ">" not in out  # no hard truncation marker
    # The content should still be present (possibly across lines)
    assert "x" in out
