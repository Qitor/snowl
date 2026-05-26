"""Top-level operator CLI entrypoint that wires commands into eval, bench, retry, and monitor flows.

Framework role:
- Owns user-facing command UX, flag parsing, process lifecycle, and web monitor bootstrap behavior.

Runtime/usage wiring:
- Delegates domain logic into lower layers (`snowl.eval`, `snowl.bench`, `snowl.web.*`).
- Command implementations are in ``snowl.cli_modules`` sub-package.

Change guardrails:
- Keep business/runtime semantics in lower layers; this file should orchestrate, not re-implement.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

from snowl.bench import check_benchmark_conformance, list_benchmarks, run_benchmark, scaffold_benchmark
from snowl.eval import EvalRunBootstrap, retry_run, run_eval
from snowl.examples_lint import validate_examples_layout
from snowl.project_config import find_project_file, load_project_config
from snowl.suite import check_suite_config, run_suite
from snowl.ui import ConsoleRenderer, InteractionController, LiveConsoleRenderer
from snowl.web.runtime import WebRuntimeError, current_webui_cache_key, ensure_next_build, ensure_next_runtime


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [x.strip() for x in value.split(",") if x.strip()]
    return parts or None


def _project_base_dir(path: str) -> Path:
    p = Path(path).resolve()
    project_file = find_project_file(p)
    if project_file is not None:
        try:
            return load_project_config(project_file).root_dir
        except Exception:
            return project_file.parent
    return p if p.is_dir() else p.parent


def _latest_run_log_path(base_dir: Path) -> Path | None:
    runs_dir = base_dir / ".snowl" / "runs"
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for child in runs_dir.iterdir():
        log_path = child / "run.log"
        if child.is_dir() and log_path.exists():
            try:
                mtime = log_path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, log_path))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _print_interrupt_log_hint(base_dir: Path) -> None:
    log_path = _latest_run_log_path(base_dir)
    print("Interrupted by user.")
    if log_path is not None:
        print(f"log={log_path}")
    else:
        print(f"log_dir={base_dir / '.snowl' / 'runs'}")


def _close_renderer(renderer: object | None) -> None:
    if renderer is None:
        return
    close = getattr(renderer, "close", None)
    if callable(close):
        try:
            close()
            return
        except Exception:
            pass
    # Fallback for LiveConsoleRenderer internals to ensure rich alt-screen is released.
    rich_live = getattr(renderer, "_rich_live", None)
    if rich_live is not None:
        try:
            rich_live.stop()
        except Exception:
            pass


def _port_listening(host: str, port: int, *, timeout_sec: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout_sec)):
            return True
    except Exception:
        return False


def _monitor_health(host: str, port: int, *, timeout_sec: float = 0.35) -> dict[str, object] | None:
    url = f"http://{host}:{int(port)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=float(timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _env_float(name: str, *, default: float, minimum: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return float(default)
    try:
        parsed = float(raw)
    except Exception:
        return float(default)
    return parsed if parsed >= float(minimum) else float(default)


def _wait_for_monitor_ready(
    *,
    host: str,
    port: int,
    process: subprocess.Popen[bytes] | None = None,
    timeout_sec: float = 8.0,
    poll_sec: float = 0.2,
    settle_sec: float = 0.35,
) -> bool:
    """Wait until monitor health endpoint responds, then keep a short settle window."""

    deadline = time.time() + max(0.2, float(timeout_sec))
    poll = max(0.05, float(poll_sec))
    while time.time() < deadline:
        if process is not None:
            try:
                if process.poll() is not None:
                    return False
            except Exception:
                pass
        if _port_listening(host, port, timeout_sec=0.15):
            if _monitor_health(host, port, timeout_sec=0.35) is not None:
                if settle_sec > 0:
                    time.sleep(float(settle_sec))
                return True
        time.sleep(poll)
    return False


def _same_project(lhs: str, rhs: str) -> bool:
    try:
        return Path(lhs).resolve() == Path(rhs).resolve()
    except Exception:
        return str(lhs).strip() == str(rhs).strip()


def _coerce_positive_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _parse_provider_budgets(values: list[str] | None) -> dict[str, int] | None:
    budgets: dict[str, int] = {}
    for item in values or []:
        raw = str(item or "").strip()
        if not raw or "=" not in raw:
            continue
        provider_id, limit_raw = raw.split("=", 1)
        provider_key = provider_id.strip()
        limit = _coerce_positive_int(limit_raw)
        if provider_key and limit is not None:
            budgets[provider_key] = limit
    return budgets or None


def _auto_open_browser(url: str | None) -> None:
    if not url:
        return
    try:
        webbrowser.open(url, new=2, autoraise=True)
    except Exception:
        # Best effort only; eval flow should never depend on browser availability.
        pass


def _expected_web_monitor_cache_key() -> str | None:
    try:
        return current_webui_cache_key()
    except Exception:
        return None


def _try_stop_monitor_process(*, pid: int | None, host: str, port: int, timeout_sec: float = 2.0) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(int(pid), signal.SIGTERM)
    except Exception:
        return False
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        if not _port_listening(host, port, timeout_sec=0.1):
            return True
        time.sleep(0.1)
    return not _port_listening(host, port, timeout_sec=0.1)


def _try_free_port_listener(*, host: str, port: int, timeout_sec: float = 2.0) -> bool:
    if not _port_listening(host, port, timeout_sec=0.1):
        return True
    pids: list[int] = []
    if os.name == "nt":
        return False
    try:
        done = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in (done.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
            except Exception:
                continue
            if pid > 0 and pid not in pids:
                pids.append(pid)
    except Exception:
        return False
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            continue
    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        if not _port_listening(host, port, timeout_sec=0.1):
            return True
        time.sleep(0.1)
    return not _port_listening(host, port, timeout_sec=0.1)


def _next_available_port(host: str, start_port: int, *, max_tries: int = 32) -> int | None:
    base = int(start_port)
    for delta in range(max_tries):
        candidate = base + delta
        if not _port_listening(host, candidate, timeout_sec=0.1):
            return candidate
    return None


class _ManagedWebMonitor:
    def __init__(
        self,
        *,
        project: str,
        host: str,
        port: int,
        poll_interval_sec: float,
        enabled: bool,
    ) -> None:
        self.project = str(Path(project).resolve())
        self.host = str(host)
        self.requested_port = int(port)
        self.poll_interval_sec = float(poll_interval_sec)
        self.enabled = bool(enabled)
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None

    def maybe_start(self) -> str | None:
        if not self.enabled:
            return None
        if os.getenv("SNOWL_AUTO_WEB_BOOTSTRAP", "1").lower() in {"0", "false", "off", "no"}:
            return None
        if not sys.stdout.isatty():
            return None
        if self.process is not None:
            return f"http://{self.host}:{self.port}"

        target_port = _next_available_port(self.host, self.requested_port)
        if target_port is None:
            return None

        cmd = [
            sys.executable,
            "-m",
            "snowl.cli",
            "web",
            "monitor",
            "--project",
            self.project,
            "--host",
            self.host,
            "--port",
            str(target_port),
            "--poll-interval-sec",
            str(self.poll_interval_sec),
        ]
        env = dict(os.environ)
        env["SNOWL_AUTO_WEB_BOOTSTRAP"] = "0"
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except Exception:
            self.process = None
            return None

        self.port = target_port
        url = f"http://{self.host}:{target_port}"
        _wait_for_monitor_ready(
            host=self.host,
            port=target_port,
            process=self.process,
            timeout_sec=_env_float(
                "SNOWL_WEB_MONITOR_READY_TIMEOUT_SEC",
                default=8.0,
                minimum=0.2,
            ),
            poll_sec=_env_float(
                "SNOWL_WEB_MONITOR_READY_POLL_SEC",
                default=0.2,
                minimum=0.05,
            ),
            settle_sec=_env_float(
                "SNOWL_WEB_MONITOR_READY_SETTLE_SEC",
                default=0.35,
                minimum=0.0,
            ),
        )
        return url

    def stop(self) -> None:
        proc = self.process
        if proc is None:
            return
        self.process = None
        try:
            if proc.poll() is not None:
                return
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                if proc.poll() is not None:
                    return
            except Exception:
                return
            time.sleep(0.1)
        try:
            proc.kill()
        except Exception:
            pass


@contextlib.contextmanager
def _interrupt_on_sigterm():
    handlers: dict[int, object] = {}

    def _handler(_signum, _frame):
        raise KeyboardInterrupt

    for sig_name in ("SIGTERM",):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            handlers[int(sig)] = signal.getsignal(sig)
            signal.signal(sig, _handler)
        except Exception:
            continue
    try:
        yield
    finally:
        for sig_num, handler in handlers.items():
            try:
                signal.signal(signal.Signals(sig_num), handler)
            except Exception:
                continue


def _print_run_bootstrap(prefix: str, info: EvalRunBootstrap) -> None:
    print(f"{prefix}: run_id={info.run_id} benchmark={info.benchmark} experiment_id={info.experiment_id}")
    print(
        "{prefix}: tasks={tasks} agents={agents} variants={variants} samples={samples} total_trials={trials}".format(
            prefix=prefix,
            tasks=info.task_count,
            agents=info.agent_count,
            variants=info.variant_count,
            samples=info.sample_count,
            trials=info.total_trials,
        )
    )
    print(f"{prefix}: artifacts={info.artifacts_dir}")
    print(f"{prefix}: log={info.log_path}")


def _maybe_autostart_web_monitor(
    *,
    project: str,
    host: str,
    port: int,
    poll_interval_sec: float,
    enabled: bool,
) -> None:
    if not enabled:
        return
    if os.getenv("SNOWL_AUTO_WEB_BOOTSTRAP", "1").lower() in {"0", "false", "off", "no"}:
        return
    if not sys.stdout.isatty():
        return
    requested_project = str(Path(project).resolve())
    expected_cache_key = _expected_web_monitor_cache_key()
    target_port = int(port)
    if _port_listening(host, target_port):
        health = _monitor_health(host, target_port)
        existing_project = str((health or {}).get("project_dir") or "").strip()
        monitor_runtime = str((health or {}).get("monitor_runtime") or "").strip().lower()
        is_next_monitor = monitor_runtime == "next"
        existing_cache_key = str((health or {}).get("cache_key") or "").strip()
        existing_pid = _coerce_positive_int((health or {}).get("pid"))
        if existing_project and _same_project(existing_project, requested_project) and is_next_monitor:
            if expected_cache_key and existing_cache_key != expected_cache_key:
                print(
                    f"Web monitor on http://{host}:{target_port} is outdated "
                    f"(running={existing_cache_key or 'unknown'}, expected={expected_cache_key}); refreshing."
                )
                if _try_stop_monitor_process(pid=existing_pid, host=host, port=target_port) or _try_free_port_listener(
                    host=host, port=target_port
                ):
                    pass
                else:
                    fallback = _next_available_port(host, target_port + 1)
                    if fallback is None:
                        print(f"Web monitor port {target_port} is occupied.")
                        return
                    print(f"Starting upgraded Web monitor on http://{host}:{fallback}")
                    target_port = int(fallback)
            else:
                print(f"Web monitor: http://{host}:{target_port}")
                return
        if _port_listening(host, target_port, timeout_sec=0.1):
            fallback = _next_available_port(host, target_port + 1)
            if fallback is None:
                if existing_project:
                    print(
                        f"Web monitor already running for {existing_project} at http://{host}:{target_port}"
                    )
                else:
                    print(f"Web monitor port {target_port} is occupied.")
                return
            if existing_project:
                if _same_project(existing_project, requested_project) and (not is_next_monitor):
                    print(
                        f"Web monitor port {target_port} is serving legacy/unknown monitor for {existing_project}; "
                        f"starting Next monitor on http://{host}:{fallback}"
                    )
                else:
                    print(
                        f"Web monitor port {target_port} is bound to {existing_project}; "
                        f"starting monitor for {requested_project} on http://{host}:{fallback}"
                    )
            else:
                print(
                    f"Web monitor port {target_port} is occupied by another process; "
                    f"starting monitor for {requested_project} on http://{host}:{fallback}"
                )
            target_port = int(fallback)

    cmd = [
        sys.executable,
        "-m",
        "snowl.cli",
        "web",
        "monitor",
        "--project",
        str(Path(project).resolve()),
        "--host",
        str(host),
        "--port",
        str(target_port),
        "--poll-interval-sec",
        str(float(poll_interval_sec)),
    ]
    env = dict(os.environ)
    env["SNOWL_AUTO_WEB_BOOTSTRAP"] = "0"
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    except Exception:
        return

    deadline = time.time() + 2.5
    print(f"Web monitor (starting): http://{host}:{target_port}")
    while time.time() < deadline:
        if _port_listening(host, target_port, timeout_sec=0.15):
            print(f"Web monitor: http://{host}:{target_port}")
            return
        time.sleep(0.1)
    print(
        f"Web monitor bootstrap is taking longer than expected on port {target_port}. "
        f"Keep http://{host}:{target_port} open and retry in a few seconds; first bootstrap may take minutes. "
        f"If it still fails, run: snowl web monitor --project {requested_project} --host {host} --port {target_port}"
    )


def _build_renderer(
    *,
    no_ui: bool,
    cli_ui: bool,
    ui_refresh_ms: int | None,
    ui_max_events: int | None,
    ui_max_failures: int | None,
    ui_max_active_trials: int | None,
    ui_refresh_profile: str | None,
    ui_theme: str | None,
    ui_mode: str | None,
    ui_no_banner: bool,
):
    if cli_ui:
        return LiveConsoleRenderer(
            verbose=True,
            refresh_interval_ms=(ui_refresh_ms if ui_refresh_ms is not None else 80),
            max_events=(ui_max_events if ui_max_events is not None else 240),
            max_failures=(ui_max_failures if ui_max_failures is not None else 120),
            max_active_trials=(ui_max_active_trials if ui_max_active_trials is not None else 48),
            ui_refresh_profile=(ui_refresh_profile or "balanced"),
            theme_mode=(ui_theme or "research"),
            ui_mode=(ui_mode or "auto"),
            show_banner=(not ui_no_banner),
        )
    if no_ui:
        return None
    return ConsoleRenderer(verbose=True)


# ---------------------------------------------------------------------------
# Command implementations — delegated to cli_modules for modularity
# ---------------------------------------------------------------------------

def _cmd_eval(*args, **kwargs):
    from snowl.cli_commands import _cmd_eval as _impl
    return _impl(*args, **kwargs)

def _cmd_retry(*args, **kwargs):
    from snowl.cli_commands import _cmd_retry as _impl
    return _impl(*args, **kwargs)

def _print_summary(*args, **kwargs):
    from snowl.cli_commands import _print_summary as _impl
    return _impl(*args, **kwargs)

def _cmd_bench_list(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_bench_list as _impl
    return _impl(*args, **kwargs)

def _cmd_bench_run(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_bench_run as _impl
    return _impl(*args, **kwargs)

def _cmd_bench_check(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_bench_check as _impl
    return _impl(*args, **kwargs)

def _cmd_bench_scaffold(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_bench_scaffold as _impl
    return _impl(*args, **kwargs)

def _cmd_suite_check(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_suite_check as _impl
    return _impl(*args, **kwargs)

def _cmd_suite_run(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_suite_run as _impl
    return _impl(*args, **kwargs)

def _cmd_examples_check(*args, **kwargs):
    from snowl.cli_modules.bench import _cmd_examples_check as _impl
    return _impl(*args, **kwargs)

def _cmd_registry_list(*args, **kwargs):
    from snowl.cli_modules.registry import _cmd_registry_list as _impl
    return _impl(*args, **kwargs)

def _cmd_registry_doctor(*args, **kwargs):
    from snowl.cli_modules.registry import _cmd_registry_doctor as _impl
    return _impl(*args, **kwargs)

def _cmd_registry_info(*args, **kwargs):
    from snowl.cli_modules.registry import _cmd_registry_info as _impl
    return _impl(*args, **kwargs)

def _cmd_leaderboard_publish(*args, **kwargs):
    from snowl.cli_modules.leaderboard import _cmd_leaderboard_publish as _impl
    return _impl(*args, **kwargs)

def _cmd_leaderboard_list(*args, **kwargs):
    from snowl.cli_modules.leaderboard import _cmd_leaderboard_list as _impl
    return _impl(*args, **kwargs)

def _cmd_leaderboard_compare(*args, **kwargs):
    from snowl.cli_modules.leaderboard import _cmd_leaderboard_compare as _impl
    return _impl(*args, **kwargs)

def _cmd_web_monitor(*args, **kwargs):
    from snowl.cli_modules.web import _cmd_web_monitor as _impl
    return _impl(*args, **kwargs)

def _resolve_run_dir(*args, **kwargs):
    from snowl.cli_modules.web import _resolve_run_dir as _impl
    return _impl(*args, **kwargs)

def _cmd_report(*args, **kwargs):
    from snowl.cli_modules.web import _cmd_report as _impl
    return _impl(*args, **kwargs)

def _cmd_compare(*args, **kwargs):
    from snowl.cli_modules.web import _cmd_compare as _impl
    return _impl(*args, **kwargs)

def _cmd_rescore(*args, **kwargs):
    from snowl.cli_modules.web import _cmd_rescore as _impl
    return _impl(*args, **kwargs)

def _cmd_export(*args, **kwargs):
    from snowl.cli_modules.web import _cmd_export as _impl
    return _impl(*args, **kwargs)

def _load_outcomes(*args, **kwargs):
    from snowl.cli_modules.web import _load_outcomes as _impl
    return _impl(*args, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snowl")
    sub = parser.add_subparsers(dest="command", required=True)

    eval_parser = sub.add_parser("eval", help="Run evaluation from a project.yml file.")
    eval_parser.add_argument("path", nargs="?", default="project.yml", help="Path to project.yml")
    eval_parser.add_argument("--task", dest="task", default=None, help="Task id selector (csv).")
    eval_parser.add_argument("--agent", dest="agent", default=None, help="Agent id selector (csv).")
    eval_parser.add_argument("--variant", dest="variant", default=None, help="Variant id selector (csv).")
    eval_parser.add_argument("--scorer", dest="scorer", default=None, help="Scorer id selector (csv).")
    eval_parser.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses plain terminal logs + background Web monitor).",
    )
    eval_parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable terminal progress output (keeps Web monitor auto-start unless --no-web-monitor is set).",
    )
    eval_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint.")
    eval_parser.add_argument(
        "--rerun-failed-only",
        action="store_true",
        help="Run only failed trials from the latest run.",
    )
    eval_parser.add_argument("--checkpoint-key", default=None, help="Checkpoint key override.")
    eval_parser.add_argument(
        "--keys",
        default=None,
        help="Simulated interactive key sequence (e.g. 'pfar') for automation/tests.",
    )
    eval_parser.add_argument("--max-running-trials", type=int, default=None, help="Max concurrently executing trials.")
    eval_parser.add_argument("--max-container-slots", type=int, default=None, help="Max concurrent container/sandbox slots.")
    eval_parser.add_argument("--max-builds", type=int, default=None, help="Max concurrent container/image builds.")
    eval_parser.add_argument("--max-scoring-tasks", type=int, default=None, help="Max concurrent scoring tasks.")
    eval_parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Preserve runtime-owned containers after the run for debugging.",
    )
    eval_parser.add_argument(
        "--keep-failed-containers",
        action="store_true",
        help="Preserve runtime-owned containers only for non-success trials.",
    )
    eval_parser.add_argument(
        "--provider-budget",
        action="append",
        default=None,
        help="Provider concurrency budget in the form provider_id=n (repeatable).",
    )
    eval_parser.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id for cross-run aggregation.",
    )
    eval_parser.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during eval.",
    )
    eval_parser.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    eval_parser.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    eval_parser.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
    eval_parser.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    eval_parser.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    eval_parser.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    eval_parser.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    eval_parser.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    eval_parser.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    eval_parser.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    eval_parser.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")

    retry_parser = sub.add_parser("retry", help="Retry unfinished and non-success trials for an existing run.")
    retry_parser.add_argument("run_id", help="Run id to recover in place.")
    retry_parser.add_argument("--project", default=".", help="Project root or project.yml used to resolve the run source.")
    retry_parser.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses plain terminal logs + background Web monitor).",
    )
    retry_parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable terminal progress output (keeps Web monitor auto-start unless --no-web-monitor is set).",
    )
    retry_parser.add_argument("--max-running-trials", type=int, default=None, help="Max concurrently executing trials.")
    retry_parser.add_argument("--max-container-slots", type=int, default=None, help="Max concurrent container/sandbox slots.")
    retry_parser.add_argument("--max-builds", type=int, default=None, help="Max concurrent container/image builds.")
    retry_parser.add_argument("--max-scoring-tasks", type=int, default=None, help="Max concurrent scoring tasks.")
    retry_parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Preserve runtime-owned containers after the retry session for debugging.",
    )
    retry_parser.add_argument(
        "--keep-failed-containers",
        action="store_true",
        help="Preserve runtime-owned containers only for non-success retry trials.",
    )
    retry_parser.add_argument(
        "--provider-budget",
        action="append",
        default=None,
        help="Provider concurrency budget in the form provider_id=n (repeatable).",
    )
    retry_parser.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id override for the recovery session.",
    )
    retry_parser.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during retry.",
    )
    retry_parser.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    retry_parser.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    retry_parser.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
    retry_parser.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    retry_parser.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    retry_parser.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    retry_parser.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    retry_parser.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    retry_parser.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    retry_parser.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    retry_parser.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")

    bench_parser = sub.add_parser("bench", help="Benchmark adapter commands.")
    bench_sub = bench_parser.add_subparsers(dest="bench_command", required=True)

    bench_list = bench_sub.add_parser("list", help="List available benchmark adapters.")

    bench_run = bench_sub.add_parser("run", help="Run benchmark tasks with local agent/scorer.")
    bench_run.add_argument("benchmark", help="Benchmark adapter name.")
    bench_run.add_argument("--project", default="project.yml", help="Path to project.yml.")
    bench_run.add_argument("--split", default="test", help="Benchmark split.")
    bench_run.add_argument("--limit", type=int, default=None, help="Max benchmark samples to load.")
    bench_run.add_argument("--adapter", default=None, help="External adapter spec in module.py:object format.")
    bench_run.add_argument(
        "--adapter-arg",
        action="append",
        default=None,
        help="Adapter arg key=value (repeatable).",
    )
    bench_run.add_argument(
        "--benchmark-filter",
        action="append",
        default=None,
        help="Benchmark row filter key=value (repeatable).",
    )
    bench_run.add_argument("--task", dest="task", default=None, help="Task id selector (csv).")
    bench_run.add_argument("--agent", dest="agent", default=None, help="Agent id selector (csv).")
    bench_run.add_argument("--variant", dest="variant", default=None, help="Variant id selector (csv).")
    bench_run.add_argument(
        "--cli-ui",
        action="store_true",
        help="Enable legacy live CLI renderer (default uses plain terminal logs + background Web monitor).",
    )
    bench_run.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable terminal progress output (keeps Web monitor auto-start unless --no-web-monitor is set).",
    )
    bench_run.add_argument("--max-running-trials", type=int, default=None, help="Max concurrently executing trials.")
    bench_run.add_argument("--max-container-slots", type=int, default=None, help="Max concurrent container/sandbox slots.")
    bench_run.add_argument("--max-builds", type=int, default=None, help="Max concurrent container/image builds.")
    bench_run.add_argument("--max-scoring-tasks", type=int, default=None, help="Max concurrent scoring tasks.")
    bench_run.add_argument(
        "--keep-containers",
        action="store_true",
        help="Preserve runtime-owned containers after benchmark run for debugging.",
    )
    bench_run.add_argument(
        "--keep-failed-containers",
        action="store_true",
        help="Preserve runtime-owned containers only for non-success benchmark trials.",
    )
    bench_run.add_argument(
        "--provider-budget",
        action="append",
        default=None,
        help="Provider concurrency budget in the form provider_id=n (repeatable).",
    )
    bench_run.add_argument(
        "--experiment-id",
        default=None,
        help="Optional experiment id for cross-run aggregation.",
    )
    bench_run.add_argument(
        "--no-web-monitor",
        action="store_true",
        help="Disable auto-start of the web monitor during benchmark runs.",
    )
    bench_run.add_argument("--web-monitor-host", default="127.0.0.1", help="Web monitor host.")
    bench_run.add_argument("--web-monitor-port", type=int, default=8765, help="Web monitor port.")
    bench_run.add_argument(
        "--web-monitor-poll-interval-sec",
        type=float,
        default=0.5,
        help="Web monitor poll interval for run discovery.",
    )
    bench_run.add_argument("--ui-refresh-ms", type=int, default=None, help="UI refresh interval in milliseconds.")
    bench_run.add_argument("--ui-max-events", type=int, default=None, help="UI event buffer max entries.")
    bench_run.add_argument("--ui-max-failures", type=int, default=None, help="UI failure buffer max entries.")
    bench_run.add_argument("--ui-max-active-trials", type=int, default=None, help="UI active trial buffer max entries.")
    bench_run.add_argument(
        "--ui-refresh-profile",
        choices=["smooth", "balanced", "low_cpu"],
        default=None,
        help="UI refresh profile.",
    )
    bench_run.add_argument(
        "--ui-theme",
        choices=["contrast", "quiet", "research", "research_redops"],
        default="research",
        help="UI theme mode.",
    )
    bench_run.add_argument(
        "--ui-mode",
        choices=["auto", "default", "qa_dense", "ops_dense", "compare_dense"],
        default=None,
        help="UI panel mode preset.",
    )
    bench_run.add_argument("--ui-no-banner", action="store_true", help="Start with banner collapsed.")

    bench_check = bench_sub.add_parser("check", help="Run benchmark adapter conformance checks.")
    bench_check.add_argument("benchmark", help="Benchmark adapter name.")
    bench_check.add_argument("--adapter", default=None, help="External adapter spec in module.py:object format.")
    bench_check.add_argument(
        "--adapter-arg",
        action="append",
        default=None,
        help="Adapter arg key=value (repeatable).",
    )

    bench_scaffold = bench_sub.add_parser("scaffold", help="Create a third-party benchmark adapter template.")
    bench_scaffold.add_argument("name", help="Benchmark name for the scaffold.")
    bench_scaffold.add_argument("--out", required=True, help="Output directory for scaffold files.")

    suite_parser = sub.add_parser("suite", help="Multi-benchmark suite commands.")
    suite_sub = suite_parser.add_subparsers(dest="suite_command", required=True)
    suite_check = suite_sub.add_parser("check", help="Validate a suite.yml file.")
    suite_check.add_argument("path", help="Path to suite.yml.")
    suite_run = suite_sub.add_parser("run", help="Run benchmarks listed in a suite.yml file.")
    suite_run.add_argument("path", help="Path to suite.yml.")

    examples_parser = sub.add_parser("examples", help="Examples validation commands.")
    examples_sub = examples_parser.add_subparsers(dest="examples_command", required=True)
    examples_check = examples_sub.add_parser("check", help="Validate examples folder layout.")
    examples_check.add_argument("path", nargs="?", default="examples", help="Examples root path.")

    web_parser = sub.add_parser("web", help="Web monitor commands.")
    web_sub = web_parser.add_subparsers(dest="web_command", required=True)
    web_monitor = web_sub.add_parser("monitor", help="Start local web monitor (SSE).")
    web_monitor.add_argument("--project", default=".", help="Project root path.")
    web_monitor.add_argument("--host", default="127.0.0.1", help="Bind host.")
    web_monitor.add_argument("--port", type=int, default=8765, help="Bind port.")
    web_monitor.add_argument(
        "--poll-interval-sec",
        type=float,
        default=0.5,
        help="Background run discovery poll interval.",
    )

    report_parser = sub.add_parser("report", help="Regenerate report from a previous run.")
    report_parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    report_parser.add_argument("--project", default=".", help="Project root path.")
    report_parser.add_argument("--format", choices=["html", "json", "markdown"], default="html", help="Output format.")
    report_parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout for json/markdown, overwrite report.html for html).")

    compare_parser = sub.add_parser("compare", help="Compare results from two runs.")
    compare_parser.add_argument("run_id_a", help="First run id.")
    compare_parser.add_argument("run_id_b", help="Second run id.")
    compare_parser.add_argument("--project", default=".", help="Project root path.")
    compare_parser.add_argument("--format", choices=["html", "markdown", "json"], default="markdown", help="Output format.")
    compare_parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout).")

    rescore_parser = sub.add_parser("rescore", help="Re-score trials from a previous run.")
    rescore_parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    rescore_parser.add_argument("--project", default=".", help="Project root path.")
    rescore_parser.add_argument("--scorer", default=None, help="Scorer id selector (csv). Only re-score with these scorers.")

    export_parser = sub.add_parser("export", help="Export trial trace data in portable formats.")
    export_parser.add_argument("run_id", nargs="?", default="latest", help="Run id or 'latest'.")
    export_parser.add_argument("--project", "-p", default=".", help="Project root path.")
    export_parser.add_argument("--format", choices=["openai", "json", "jsonl"], default="openai", help="Export format (default: openai).")
    export_parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout).")
    export_parser.add_argument("--trial-key", default=None, help="Export a specific trial only.")

    registry_parser = sub.add_parser("registry", help="Registry inspection and diagnostics.")
    registry_sub = registry_parser.add_subparsers(dest="registry_command", required=True)
    registry_list = registry_sub.add_parser("list", help="List all registered components.")
    registry_list.add_argument("--kind", choices=["benchmark", "adapter", "environment_provider"], default=None, help="Filter by component kind.")
    registry_doctor = registry_sub.add_parser("doctor", help="Run registry health diagnostics.")
    registry_info = registry_sub.add_parser("info", help="Show details for a named component.")
    registry_info.add_argument("name", help="Component name to look up.")

    # --- leaderboard ---
    leaderboard_parser = sub.add_parser("leaderboard", help="Leaderboard operations: publish, list, compare.")
    leaderboard_sub = leaderboard_parser.add_subparsers(dest="leaderboard_command", required=True)
    lb_publish = leaderboard_sub.add_parser("publish", help="Publish run results to leaderboard.")
    lb_publish.add_argument("run_dir", help="Path to the run artifacts directory.")
    lb_list = leaderboard_sub.add_parser("list", help="List leaderboard entries.")
    lb_list.add_argument("--domain", default=None, help="Filter by domain.")
    lb_list.add_argument("--top", type=int, default=20, help="Show top N entries.")
    lb_compare = leaderboard_sub.add_parser("compare", help="Compare two runs on the leaderboard.")
    lb_compare.add_argument("run_dir_a", help="Path to first run artifacts directory.")
    lb_compare.add_argument("run_dir_b", help="Path to second run artifacts directory.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "eval":
        return _cmd_eval(
            str(Path(args.path)),
            task=args.task,
            agent=args.agent,
            variant=args.variant,
            scorer=args.scorer,
            no_ui=args.no_ui,
            resume=args.resume,
            rerun_failed_only=args.rerun_failed_only,
            checkpoint_key=args.checkpoint_key,
            keys=args.keys,
            max_running_trials=args.max_running_trials,
            max_container_slots=args.max_container_slots,
            max_builds=args.max_builds,
            max_scoring_tasks=args.max_scoring_tasks,
            provider_budget=args.provider_budget,
            keep_containers=bool(args.keep_containers),
            keep_failed_containers=bool(args.keep_failed_containers),
            ui_refresh_ms=args.ui_refresh_ms,
            ui_max_events=args.ui_max_events,
            ui_max_failures=args.ui_max_failures,
            ui_max_active_trials=args.ui_max_active_trials,
            ui_refresh_profile=args.ui_refresh_profile,
            ui_theme=args.ui_theme,
            ui_mode=args.ui_mode,
            ui_no_banner=args.ui_no_banner,
            experiment_id=args.experiment_id,
            web_monitor=(not args.no_web_monitor),
            web_monitor_host=args.web_monitor_host,
            web_monitor_port=args.web_monitor_port,
            web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
            cli_ui=bool(args.cli_ui),
        )

    if args.command == "bench":
        if args.bench_command == "list":
            return _cmd_bench_list()
        if args.bench_command == "run":
            return _cmd_bench_run(
                args.benchmark,
                project=str(Path(args.project)),
                split=args.split,
                limit=args.limit,
                adapter=args.adapter,
                adapter_arg=args.adapter_arg,
                benchmark_filter=args.benchmark_filter,
                task=args.task,
                agent=args.agent,
                variant=args.variant,
                no_ui=args.no_ui,
                max_running_trials=args.max_running_trials,
                max_container_slots=args.max_container_slots,
                max_builds=args.max_builds,
                max_scoring_tasks=args.max_scoring_tasks,
                provider_budget=args.provider_budget,
                keep_containers=bool(args.keep_containers),
                keep_failed_containers=bool(args.keep_failed_containers),
                ui_refresh_ms=args.ui_refresh_ms,
                ui_max_events=args.ui_max_events,
                ui_max_failures=args.ui_max_failures,
                ui_max_active_trials=args.ui_max_active_trials,
                ui_refresh_profile=args.ui_refresh_profile,
                ui_theme=args.ui_theme,
                ui_mode=args.ui_mode,
                ui_no_banner=args.ui_no_banner,
                experiment_id=args.experiment_id,
                web_monitor=(not args.no_web_monitor),
                web_monitor_host=args.web_monitor_host,
                web_monitor_port=args.web_monitor_port,
                web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
                cli_ui=bool(args.cli_ui),
            )
        if args.bench_command == "check":
            return _cmd_bench_check(args.benchmark, adapter=args.adapter, adapter_arg=args.adapter_arg)
        if args.bench_command == "scaffold":
            return _cmd_bench_scaffold(args.name, out=args.out)

    if args.command == "suite":
        if args.suite_command == "check":
            return _cmd_suite_check(args.path)
        if args.suite_command == "run":
            return _cmd_suite_run(args.path)

    if args.command == "examples":
        if args.examples_command == "check":
            return _cmd_examples_check(str(Path(args.path)))

    if args.command == "retry":
        return _cmd_retry(
            str(args.run_id),
            project=str(Path(args.project)),
            no_ui=args.no_ui,
            max_running_trials=args.max_running_trials,
            max_container_slots=args.max_container_slots,
            max_builds=args.max_builds,
            max_scoring_tasks=args.max_scoring_tasks,
            provider_budget=args.provider_budget,
            keep_containers=bool(args.keep_containers),
            keep_failed_containers=bool(args.keep_failed_containers),
            ui_refresh_ms=args.ui_refresh_ms,
            ui_max_events=args.ui_max_events,
            ui_max_failures=args.ui_max_failures,
            ui_max_active_trials=args.ui_max_active_trials,
            ui_refresh_profile=args.ui_refresh_profile,
            ui_theme=args.ui_theme,
            ui_mode=args.ui_mode,
            ui_no_banner=args.ui_no_banner,
            experiment_id=args.experiment_id,
            web_monitor=(not args.no_web_monitor),
            web_monitor_host=args.web_monitor_host,
            web_monitor_port=args.web_monitor_port,
            web_monitor_poll_interval_sec=args.web_monitor_poll_interval_sec,
            cli_ui=bool(args.cli_ui),
        )

    if args.command == "web":
        if args.web_command == "monitor":
            return _cmd_web_monitor(
                project=str(Path(args.project)),
                host=str(args.host),
                port=int(args.port),
                poll_interval_sec=float(args.poll_interval_sec),
            )

    if args.command == "report":
        return _cmd_report(
            args.run_id,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
        )

    if args.command == "compare":
        return _cmd_compare(
            args.run_id_a,
            args.run_id_b,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
        )

    if args.command == "rescore":
        return _cmd_rescore(
            args.run_id,
            project=str(Path(args.project)),
            scorer=args.scorer,
        )

    if args.command == "export":
        return _cmd_export(
            args.run_id,
            project=str(Path(args.project)),
            format=args.format,
            output=args.output,
            trial_key=args.trial_key,
        )

    if args.command == "registry":
        if args.registry_command == "list":
            return _cmd_registry_list(kind=args.kind)
        if args.registry_command == "doctor":
            return _cmd_registry_doctor()
        if args.registry_command == "info":
            return _cmd_registry_info(args.name)

    if args.command == "leaderboard":
        if args.leaderboard_command == "publish":
            return _cmd_leaderboard_publish(args.run_dir)
        if args.leaderboard_command == "list":
            return _cmd_leaderboard_list(domain=args.domain, top=args.top)
        if args.leaderboard_command == "compare":
            return _cmd_leaderboard_compare(args.run_dir_a, args.run_dir_b)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
