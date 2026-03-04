from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from threading import Thread

from snowl.ui import ConsoleRenderer


@dataclass(frozen=True)
class _Plan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    sample_count: int
    trials: list[str]


@dataclass(frozen=True)
class _Summary:
    total: int
    success: int
    incorrect: int
    error: int
    limit_exceeded: int
    cancelled: int


@dataclass(frozen=True)
class _Trial:
    task_id: str
    agent_id: str
    sample_id: str | None


class _Status:
    value = "success"


class _Usage:
    total_tokens = 4


class _TaskResult:
    status = _Status()
    usage = _Usage()


class _Outcome:
    task_result = _TaskResult()
    trace = {"trace_events": [{"event": "agent.run"}, {"event": "scorer.score"}]}


class _Aggregate:
    matrix = {"t1": {"a1": {"accuracy": 1.0, "latency": 0.9}}}


def test_console_renderer_golden_snapshot_key_screens() -> None:
    renderer = ConsoleRenderer(verbose=True, width=120)
    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_plan(_Plan("single", ["t1"], ["a1"], 1, ["trial-1"]))
        renderer.render_controls()
        renderer.render_trial_start(_Trial("t1", "a1", "s1"), 1, 1)
        renderer.render_trial_finish(_Outcome())
        renderer.render_global(done=1, total=1, success=1, incorrect=0, other=0)
        renderer.render_compare(_Aggregate())
        renderer.render_summary(_Summary(1, 1, 0, 0, 0, 0), "/tmp/run", "snowl eval .")

    assert buf.getvalue() == (
        "\n"
        "=== Plan ===\n"
        "mode=single tasks=1 agents=1 variants=0 samples=1 total_trials=1\n"
        "\n"
        "=== Controls ===\n"
        "keys: p=pause/resume, f=focus-failed, a=group-agent, t=group-task, r=rerun-failed\n"
        "\n"
        "=== Trial ===\n"
        "[1/1] task=t1 agent=a1 variant=default sample=s1\n"
        "status=success latest_trace=scorer.score tokens=4\n"
        "\n"
        "=== Global ===\n"
        "progress=1/1 success=1 incorrect=0 other=0\n"
        "\n"
        "=== Compare ===\n"
        "task=t1 agent=a1 accuracy=1.000, latency=0.900\n"
        "\n"
        "=== Summary ===\n"
        "total=1 success=1 incorrect=0 error=0 limit_exceeded=0 cancelled=0\n"
        "artifacts=/tmp/run\n"
        "log=/tmp/run/run.log\n"
        "rerun=snowl eval .\n"
    )


def test_console_renderer_narrow_terminal_truncates_lines() -> None:
    renderer = ConsoleRenderer(verbose=True, width=28)
    buf = io.StringIO()
    with redirect_stdout(buf):
        renderer.render_summary(
            _Summary(10, 9, 1, 0, 0, 0),
            "/tmp/path/that/is/very/long",
            "snowl eval . --task very-long-task-id",
        )

    for line in buf.getvalue().splitlines():
        assert len(line) <= 28


def test_console_renderer_concurrent_updates_stay_structured() -> None:
    renderer = ConsoleRenderer(verbose=True, width=80)
    buf = io.StringIO()

    def _worker(offset: int) -> None:
        for i in range(10):
            renderer.render_global(done=i + offset, total=20, success=i, incorrect=0, other=0)

    with redirect_stdout(buf):
        t1 = Thread(target=_worker, args=(0,))
        t2 = Thread(target=_worker, args=(10,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    lines = [line for line in buf.getvalue().splitlines() if line]
    assert len(lines) == 40
    assert all(line == "=== Global ===" or line.startswith("progress=") for line in lines)
