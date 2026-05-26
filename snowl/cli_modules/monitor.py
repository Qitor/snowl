"""Web monitor management for the Snowl CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from snowl.cli_modules.util import (
    _auto_open_browser,
    _coerce_positive_int,
    _env_float,
    _expected_web_monitor_cache_key,
    _next_available_port,
    _port_listening,
    _same_project,
    _try_free_port_listener,
    _try_stop_monitor_process,
    _wait_for_monitor_ready,
)


def _monitor_health(host: str, port: int, *, timeout_sec: float = 0.35) -> dict[str, object] | None:
    import urllib.request
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
