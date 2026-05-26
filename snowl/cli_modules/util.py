"""Shared utility functions for the Snowl CLI."""

from __future__ import annotations

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

from snowl.project_config import find_project_file, load_project_config


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
            from snowl.cli_modules.monitor import _monitor_health
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
        pass


def _expected_web_monitor_cache_key() -> str | None:
    try:
        from snowl.web.runtime import current_webui_cache_key
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


def _print_run_bootstrap(prefix: str, info) -> None:
    """Print run bootstrap information."""
    from snowl.eval import EvalRunBootstrap
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
