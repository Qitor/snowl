from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.cli import main


def _write_project_yml(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text(
        """
project:
  name: cli-demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models:
    - id: tested
      model: demo-model
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
""",
        encoding="utf-8",
    )


def _latest_run_dir(tmp_path: Path) -> Path:
    runs_root = tmp_path / ".snowl" / "runs"
    run_dirs = sorted([p for p in runs_root.iterdir() if p.is_dir() and p.name != "by_run_id"])
    assert run_dirs
    return run_dirs[-1]


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
    _write_project_yml(tmp_path)

    rc = main(["eval", str(tmp_path / "project.yml")])
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
    _write_project_yml(tmp_path)
    rc = main(
        [
            "eval",
            str(tmp_path / "project.yml"),
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


def test_cli_eval_accepts_scheduler_flags(tmp_path: Path) -> None:
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
    _write_project_yml(tmp_path)
    rc = main(
        [
            "eval",
            str(tmp_path / "project.yml"),
            "--no-ui",
            "--max-running-trials",
            "2",
            "--max-container-slots",
            "1",
            "--max-builds",
            "1",
            "--max-scoring-tasks",
            "2",
            "--provider-budget",
            "demo=2",
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
    _write_project_yml(tmp_path)
    rc = main(["eval", str(tmp_path / "project.yml"), "--no-ui"])
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

    _write_project_yml(tmp_path)
    rc = main(["eval", str(tmp_path / "project.yml"), "--no-ui", "--experiment-id", "exp-cli"])
    assert rc == 0

    runs_root = tmp_path / ".snowl" / "runs"
    run_dirs = sorted([p for p in runs_root.iterdir() if p.is_dir() and p.name != "by_run_id"])
    assert run_dirs
    manifest = json.loads((run_dirs[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "exp-cli"


def test_cli_retry_reuses_run_id_and_recovers_failed_trial(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (state, context, tools)
        raise RuntimeError("provider unavailable")
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
    _write_project_yml(tmp_path)

    rc = main(["eval", str(tmp_path / "project.yml"), "--no-ui", "--no-web-monitor"])
    assert rc == 1
    run_dir = _latest_run_dir(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_id = manifest["run_id"]

    outcomes_before = json.loads((run_dir / "outcomes.json").read_text(encoding="utf-8"))
    assert len(outcomes_before) == 1
    assert outcomes_before[0]["task_result"]["status"] == "error"

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

    rc = main(["retry", run_id, "--project", str(tmp_path / "project.yml"), "--no-ui", "--no-web-monitor"])
    assert rc == 0

    outcomes_after = json.loads((run_dir / "outcomes.json").read_text(encoding="utf-8"))
    assert len(outcomes_after) == 1
    assert outcomes_after[0]["task_result"]["status"] == "success"

    recovery = json.loads((run_dir / "recovery.json").read_text(encoding="utf-8"))
    trial_key = "t1::a1::default::s1"
    assert trial_key in recovery["attempts_by_trial"]
    assert len(recovery["attempts_by_trial"][trial_key]) >= 2
    effective_attempt_id = recovery["effective_attempts"][trial_key]
    effective_rows = [row for row in recovery["attempts_by_trial"][trial_key] if row["attempt_id"] == effective_attempt_id]
    assert effective_rows and effective_rows[0]["status"] == "success"


def test_eval_auto_retry_recovers_within_same_run(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task
task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1","input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from pathlib import Path
from snowl.core import StopReason

COUNTER = Path(__file__).with_name("attempt_counter.txt")

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        count = int(COUNTER.read_text(encoding="utf-8")) if COUNTER.exists() else 0
        count += 1
        COUNTER.write_text(str(count), encoding="utf-8")
        if count == 1:
            raise RuntimeError("transient provider failure")
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
    (tmp_path / "project.yml").write_text(
        """
project:
  name: auto-retry
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models:
    - id: tested
      model: demo-model
eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
runtime:
  recovery:
    auto_retry_non_success: true
    max_auto_retries_per_trial: 1
    retry_timing: deferred
    backoff_ms: 1
""",
        encoding="utf-8",
    )

    rc = main(["eval", str(tmp_path / "project.yml"), "--no-ui", "--no-web-monitor"])
    assert rc == 0

    run_dir = _latest_run_dir(tmp_path)
    recovery = json.loads((run_dir / "recovery.json").read_text(encoding="utf-8"))
    trial_key = "t1::a1::default::s1"
    attempts = recovery["attempts_by_trial"][trial_key]
    assert len(attempts) == 2
    assert attempts[0]["retry_source"] == "initial_run"
    assert attempts[0]["superseded_by_attempt_id"] == attempts[1]["attempt_id"]
    assert attempts[1]["retry_source"] == "auto_retry"
    assert attempts[1]["status"] == "success"
    assert attempts[1]["effective"] is True

    outcomes = json.loads((run_dir / "outcomes.json").read_text(encoding="utf-8"))
    assert len(outcomes) == 1
    assert outcomes[0]["task_result"]["status"] == "success"


def test_cli_web_monitor_missing_deps_returns_2(monkeypatch, tmp_path: Path) -> None:
    import snowl.cli as cli_mod
    from snowl.web.runtime import WebRuntimeError

    monkeypatch.setattr(cli_mod, "ensure_next_runtime", lambda log=None: (_ for _ in ()).throw(WebRuntimeError("node missing")))
    rc = main(["web", "monitor", "--project", str(tmp_path)])
    assert rc == 2


def test_auto_web_monitor_prints_url_when_port_is_ready(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod, "_expected_web_monitor_cache_key", lambda: "k1")
    monkeypatch.setattr(cli_mod, "_port_listening", lambda host, port, timeout_sec=0.25: True)
    monkeypatch.setattr(
        cli_mod,
        "_monitor_health",
        lambda host, port, timeout_sec=0.35: {"project_dir": str(tmp_path), "monitor_runtime": "next", "cache_key": "k1"},
    )
    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8765" in out


def test_cli_web_monitor_prints_url(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    launched: dict[str, object] = {}

    class _Runtime:
        app_dir = tmp_path
        cache_key = "cache-1"
        source_dir = tmp_path / "src"
        source_mode = "repo"

    monkeypatch.setattr(cli_mod, "ensure_next_runtime", lambda log=None: _Runtime())
    monkeypatch.setattr(cli_mod, "ensure_next_build", lambda runtime, log=None: None)

    def _fake_run(cmd, cwd=None, env=None, check=False):
        launched["cmd"] = list(cmd)
        launched["cwd"] = cwd
        launched["env"] = dict(env or {})
        launched["check"] = check
        class _Done:
            returncode = 0
        return _Done()

    monkeypatch.setattr(cli_mod.subprocess, "run", _fake_run)

    rc = main(["web", "monitor", "--project", str(tmp_path), "--host", "127.0.0.1", "--port", "9999"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "http://127.0.0.1:9999" in out
    assert launched["cmd"] == ["npm", "run", "start", "--", "--hostname", "127.0.0.1", "--port", "9999"]
    assert launched["cwd"] == str(tmp_path)
    assert launched["env"]["SNOWL_PROJECT_DIR"] == str(tmp_path.resolve())
    assert launched["env"]["SNOWL_WEB_CACHE_KEY"] == "cache-1"
    assert launched["env"]["SNOWL_WEB_SOURCE_MODE"] == "repo"
    cfg = json.loads((tmp_path / ".snowl-monitor.json").read_text(encoding="utf-8"))
    assert cfg["project_dir"] == str(tmp_path.resolve())
    assert float(cfg["poll_interval_sec"]) == 0.5
    assert cfg["cache_key"] == "cache-1"
    assert cfg["source_mode"] == "repo"


def test_cli_web_monitor_dev_mode_skips_build(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    class _Runtime:
        app_dir = tmp_path
        cache_key = "cache-dev"
        source_dir = tmp_path / "src"
        source_mode = "repo"

    monkeypatch.setattr(cli_mod, "ensure_next_runtime", lambda log=None: _Runtime())
    called = {"build": 0}

    def _fake_build(runtime, log=None):
        _ = runtime, log
        called["build"] += 1

    def _fake_run(cmd, cwd=None, env=None, check=False):
        _ = cwd, env, check
        class _Done:
            returncode = 0
        assert cmd[2] == "dev"
        return _Done()

    monkeypatch.setattr(cli_mod, "ensure_next_build", _fake_build)
    monkeypatch.setattr(cli_mod.subprocess, "run", _fake_run)
    monkeypatch.setenv("SNOWL_WEB_DEV", "1")

    rc = main(["web", "monitor", "--project", str(tmp_path), "--host", "127.0.0.1", "--port", "8876"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ensure build: skipped" in out
    assert called["build"] == 0


def test_autostart_stale_monitor_same_project_uses_fallback(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod, "_expected_web_monitor_cache_key", lambda: "new-cache")
    monkeypatch.setattr(
        cli_mod,
        "_port_listening",
        lambda host, port, timeout_sec=0.25: bool(int(port) in {8765}),
    )
    monkeypatch.setattr(
        cli_mod,
        "_monitor_health",
        lambda host, port, timeout_sec=0.35: {"project_dir": str(tmp_path), "monitor_runtime": "next", "cache_key": "old-cache"},
    )
    monkeypatch.setattr(cli_mod, "_try_stop_monitor_process", lambda pid, host, port, timeout_sec=2.0: False)
    monkeypatch.setattr(cli_mod, "_try_free_port_listener", lambda host, port, timeout_sec=2.0: False)

    launched = {}

    class _P:
        def __init__(self) -> None:
            self.pid = 2026

    def _fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=None):
        _ = (stdout, stderr, env, start_new_session)
        launched["cmd"] = list(cmd)
        return _P()

    monkeypatch.setattr(cli_mod.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _x: None)
    ticks = {"n": 0}

    def _fake_time() -> float:
        ticks["n"] += 1
        return ticks["n"] * 0.5

    monkeypatch.setattr(cli_mod.time, "time", _fake_time)

    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "is outdated" in out
    assert "http://127.0.0.1:8766" in out
    assert launched["cmd"][launched["cmd"].index("--port") + 1] == "8766"


def test_autostart_stale_monitor_same_project_reclaims_same_port(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod, "_expected_web_monitor_cache_key", lambda: "new-cache")

    state = {"occupied": True}

    def _fake_port_listening(host, port, timeout_sec=0.25):
        _ = (host, timeout_sec)
        if int(port) == 8765:
            return bool(state["occupied"])
        return False

    monkeypatch.setattr(cli_mod, "_port_listening", _fake_port_listening)
    monkeypatch.setattr(
        cli_mod,
        "_monitor_health",
        lambda host, port, timeout_sec=0.35: {"project_dir": str(tmp_path), "monitor_runtime": "next", "cache_key": "old-cache"},
    )
    monkeypatch.setattr(cli_mod, "_try_stop_monitor_process", lambda pid, host, port, timeout_sec=2.0: False)

    def _fake_free(host, port, timeout_sec=2.0):
        _ = (host, timeout_sec)
        if int(port) == 8765:
            state["occupied"] = False
            return True
        return False

    monkeypatch.setattr(cli_mod, "_try_free_port_listener", _fake_free)

    launched = {}

    class _P:
        def __init__(self) -> None:
            self.pid = 2333

    def _fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=None):
        _ = (stdout, stderr, env, start_new_session)
        launched["cmd"] = list(cmd)
        return _P()

    monkeypatch.setattr(cli_mod.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _x: None)
    ticks = {"n": 0}

    def _fake_time() -> float:
        ticks["n"] += 1
        return ticks["n"] * 0.5

    monkeypatch.setattr(cli_mod.time, "time", _fake_time)

    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "is outdated" in out
    assert launched["cmd"][launched["cmd"].index("--port") + 1] == "8765"


def test_autostart_prints_starting_url_when_bootstrap_slow(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod, "_port_listening", lambda host, port, timeout_sec=0.25: False)

    class _P:
        def __init__(self) -> None:
            self.pid = 3030

    monkeypatch.setattr(cli_mod.subprocess, "Popen", lambda *args, **kwargs: _P())
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _x: None)
    ticks = {"n": 0}

    def _fake_time() -> float:
        ticks["n"] += 1
        return ticks["n"] * 0.6

    monkeypatch.setattr(cli_mod.time, "time", _fake_time)

    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "Web monitor (starting): http://127.0.0.1:8765" in out
    assert "first bootstrap may take minutes" in out


def test_eval_default_uses_plain_console_renderer(monkeypatch, tmp_path: Path) -> None:
    import snowl.cli as cli_mod

    seen = {"renderer_type": None}

    class _Summary:
        total = 1
        success = 1
        incorrect = 0
        error = 0
        limit_exceeded = 0
        cancelled = 0

    class _Result:
        summary = _Summary()
        artifacts_dir = str(tmp_path / ".snowl" / "runs" / "r")
        rerun_command = "snowl eval ."

    async def _fake_run_eval(*_args, **kwargs):
        seen["renderer_type"] = type(kwargs.get("renderer")).__name__
        return _Result()

    monkeypatch.setattr(cli_mod, "run_eval", _fake_run_eval)
    rc = main(["eval", str(tmp_path), "--no-web-monitor"])
    assert rc == 0
    assert seen["renderer_type"] == "ConsoleRenderer"


def test_eval_cli_ui_flag_enables_legacy_renderer(monkeypatch, tmp_path: Path) -> None:
    import snowl.cli as cli_mod

    seen = {"renderer_type": None}

    class _Summary:
        total = 1
        success = 1
        incorrect = 0
        error = 0
        limit_exceeded = 0
        cancelled = 0

    class _Result:
        summary = _Summary()
        artifacts_dir = str(tmp_path / ".snowl" / "runs" / "r")
        rerun_command = "snowl eval ."

    async def _fake_run_eval(*_args, **kwargs):
        seen["renderer_type"] = type(kwargs.get("renderer")).__name__
        return _Result()

    monkeypatch.setattr(cli_mod, "run_eval", _fake_run_eval)
    rc = main(["eval", str(tmp_path), "--cli-ui", "--no-web-monitor"])
    assert rc == 0
    assert seen["renderer_type"] == "LiveConsoleRenderer"


def test_autostart_web_monitor_uses_fallback_port_for_other_project(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        cli_mod,
        "_port_listening",
        lambda host, port, timeout_sec=0.25: bool(int(port) in {8765, 8766}),
    )
    monkeypatch.setattr(
        cli_mod,
        "_monitor_health",
        lambda host, port, timeout_sec=0.35: {"project_dir": "/tmp/another-project"} if int(port) == 8765 else None,
    )
    launched = {}

    class _P:
        def __init__(self) -> None:
            self.pid = 12345

    def _fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=None):
        _ = (stdout, stderr, env, start_new_session)
        launched["cmd"] = list(cmd)
        return _P()

    monkeypatch.setattr(cli_mod.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _x: None)
    ticks = {"n": 0}
    def _fake_time() -> float:
        ticks["n"] += 1
        return ticks["n"] * 0.5
    monkeypatch.setattr(cli_mod.time, "time", _fake_time)

    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "bound to /tmp/another-project" in out
    assert "http://127.0.0.1:8767" in out
    assert launched["cmd"][launched["cmd"].index("--port") + 1] == "8767"


def test_autostart_web_monitor_legacy_same_project_uses_fallback(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod

    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        cli_mod,
        "_port_listening",
        lambda host, port, timeout_sec=0.25: bool(int(port) in {8765, 8766}),
    )
    monkeypatch.setattr(
        cli_mod,
        "_monitor_health",
        lambda host, port, timeout_sec=0.35: {"project_dir": str(tmp_path)} if int(port) == 8765 else None,
    )
    launched = {}

    class _P:
        def __init__(self) -> None:
            self.pid = 2222

    def _fake_popen(cmd, stdout=None, stderr=None, env=None, start_new_session=None):
        _ = (stdout, stderr, env, start_new_session)
        launched["cmd"] = list(cmd)
        return _P()

    monkeypatch.setattr(cli_mod.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _x: None)
    ticks = {"n": 0}

    def _fake_time() -> float:
        ticks["n"] += 1
        return ticks["n"] * 0.5

    monkeypatch.setattr(cli_mod.time, "time", _fake_time)

    cli_mod._maybe_autostart_web_monitor(
        project=str(tmp_path),
        host="127.0.0.1",
        port=8765,
        poll_interval_sec=0.5,
        enabled=True,
    )
    out = capsys.readouterr().out
    assert "legacy/unknown monitor" in out
    assert "http://127.0.0.1:8767" in out
    assert launched["cmd"][launched["cmd"].index("--port") + 1] == "8767"


def test_eval_starts_managed_monitor_on_run_bootstrap(monkeypatch, tmp_path: Path, capsys) -> None:
    import snowl.cli as cli_mod
    from snowl.eval import EvalRunBootstrap

    nested = tmp_path / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    fake_file = nested / "tasks.json"
    fake_file.write_text("{}", encoding="utf-8")

    captured = {"project": None, "started": 0, "stopped": 0, "opened": []}

    class _FakeMonitor:
        def __init__(self, *, project, host, port, poll_interval_sec, enabled):
            _ = (host, port, poll_interval_sec, enabled)
            captured["project"] = project

        def maybe_start(self):
            captured["started"] += 1
            return "http://127.0.0.1:8765"

        def stop(self):
            captured["stopped"] += 1

    class _Summary:
        total = 1
        success = 1
        incorrect = 0
        error = 0
        limit_exceeded = 0
        cancelled = 0

    class _Result:
        summary = _Summary()
        artifacts_dir = str(tmp_path / ".snowl" / "runs" / "r")
        rerun_command = "snowl eval ."

    async def _fake_run_eval(*_args, **kwargs):
        callback = kwargs["on_run_bootstrap"]
        callback(
            EvalRunBootstrap(
                run_id="run-20260310T150000Z",
                experiment_id="exp-1",
                benchmark="strongreject",
                artifacts_dir=str(tmp_path / ".snowl" / "runs" / "r"),
                log_path=str(tmp_path / ".snowl" / "runs" / "r" / "run.log"),
                task_count=1,
                agent_count=1,
                variant_count=2,
                sample_count=50,
                total_trials=100,
            )
        )
        return _Result()

    monkeypatch.setattr(cli_mod, "_ManagedWebMonitor", _FakeMonitor)
    monkeypatch.setattr(cli_mod, "run_eval", _fake_run_eval)
    monkeypatch.setattr(
        cli_mod.webbrowser,
        "open",
        lambda url, new=0, autoraise=True: captured["opened"].append((url, new, autoraise)) or True,
    )

    rc = main(["eval", str(fake_file)])
    assert rc == 0
    assert captured["project"] == str(nested.resolve())
    assert captured["started"] == 1
    assert captured["stopped"] >= 1
    assert captured["opened"] == [("http://127.0.0.1:8765", 2, True)]
    out = capsys.readouterr().out
    assert "Snowl Eval: run_id=run-20260310T150000Z" in out
    assert "Web monitor: http://127.0.0.1:8765" in out


def test_eval_interrupt_stops_managed_monitor(monkeypatch, tmp_path: Path) -> None:
    import snowl.cli as cli_mod
    from snowl.eval import EvalRunBootstrap

    captured = {"started": 0, "stopped": 0}

    class _FakeMonitor:
        def __init__(self, *, project, host, port, poll_interval_sec, enabled):
            _ = (project, host, port, poll_interval_sec, enabled)

        def maybe_start(self):
            captured["started"] += 1
            return "http://127.0.0.1:8765"

        def stop(self):
            captured["stopped"] += 1

    async def _fake_run_eval(*_args, **kwargs):
        callback = kwargs["on_run_bootstrap"]
        callback(
            EvalRunBootstrap(
                run_id="run-20260310T150001Z",
                experiment_id="exp-2",
                benchmark="strongreject",
                artifacts_dir=str(tmp_path / ".snowl" / "runs" / "r"),
                log_path=str(tmp_path / ".snowl" / "runs" / "r" / "run.log"),
                task_count=1,
                agent_count=1,
                variant_count=1,
                sample_count=1,
                total_trials=1,
            )
        )
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_mod, "_ManagedWebMonitor", _FakeMonitor)
    monkeypatch.setattr(cli_mod, "run_eval", _fake_run_eval)

    rc = main(["eval", str(tmp_path)])
    assert rc == 130
    assert captured["started"] == 1
    assert captured["stopped"] >= 1
