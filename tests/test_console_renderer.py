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
    assert "=== Plan ===" in out
    assert "=== Trial ===" in out
    assert "=== Global ===" in out
    assert "=== Summary ===" in out
    assert "rerun=snowl eval ." in out


def test_console_renderer_prints_error_details(capsys) -> None:
    r = ConsoleRenderer(verbose=True)
    r.render_trial_finish(_ErrOutcome())
    out = capsys.readouterr().out
    assert "status=error" in out
    assert "error_code=agent_runtime_error" in out
