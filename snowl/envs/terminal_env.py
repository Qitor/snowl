"""Terminal environment contract and local implementation."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from queue import Empty, Queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from snowl.core import EnvSpec, validate_env_spec

_BUILD_LIMIT_LOCK = threading.Lock()
_BUILD_LIMIT_SEMAPHORE: threading.BoundedSemaphore | None = None


def set_compose_build_limit(limit: int | None) -> None:
    global _BUILD_LIMIT_SEMAPHORE
    with _BUILD_LIMIT_LOCK:
        if limit is None:
            _BUILD_LIMIT_SEMAPHORE = None
            return
        _BUILD_LIMIT_SEMAPHORE = threading.BoundedSemaphore(max(1, int(limit)))


class _BuildSemaphoreContext:
    def __init__(self, sem: threading.BoundedSemaphore | None) -> None:
        self._sem = sem

    def __enter__(self) -> None:
        if self._sem is not None:
            self._sem.acquire()
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sem is not None:
            self._sem.release()
        return None


@dataclass
class TerminalEnv:
    env_spec: EnvSpec
    workdir: str | None = None
    compose_file: str | None = None
    compose_project: str | None = None
    compose_service: str | None = None
    compose_env: dict[str, str] = field(default_factory=dict)
    compose_build: bool = True
    use_docker_compose: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)
    _last_output: str = ""
    _compose_started: bool = False

    def __post_init__(self) -> None:
        validate_env_spec(self.env_spec)
        if self.workdir is None:
            self.workdir = str(Path.cwd())
        self.workdir = str(Path(self.workdir).resolve())
        if self.compose_file:
            self.compose_file = str(Path(self.compose_file).resolve())
            self.use_docker_compose = True
        if self.compose_project is None:
            base = Path(self.workdir).name.replace("_", "-").replace(".", "-")
            self.compose_project = f"snowl-{base}-{int(time.time() * 1000) % 1000000}"
        if self.compose_service is None and self.compose_file:
            self.compose_service = self._infer_service_name(Path(self.compose_file)) or "client"
        self._ensure_compose_env()

    @property
    def env_id(self) -> str:
        return f"{self.env_spec.env_type}:terminal"

    @property
    def provided_ops(self) -> tuple[str, ...]:
        return self.env_spec.provided_ops

    def reset(self) -> dict[str, Any]:
        self.history.clear()
        self._last_output = ""
        return {"status": "reset", "workdir": self.workdir}

    def close(self) -> None:
        if self._compose_started:
            try:
                self.compose_down()
            except Exception:
                pass
        self.history.clear()
        self._compose_started = False

    def _infer_service_name(self, compose_path: Path) -> str | None:
        if not compose_path.exists():
            return None
        try:
            data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        services = data.get("services")
        if not isinstance(services, dict) or not services:
            return None
        if "client" in services:
            return "client"
        first = next(iter(services.keys()), None)
        return str(first) if first else None

    def _ensure_compose_env(self) -> None:
        if not self.use_docker_compose:
            return
        task_root = Path(self.workdir)
        logs_dir = task_root / ".snowl" / "task-logs"
        agent_logs_dir = task_root / ".snowl" / "agent-logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        agent_logs_dir.mkdir(parents=True, exist_ok=True)

        service = self.compose_service or "client"
        container_name = f"{self.compose_project}-{service}"
        defaults = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": container_name,
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": f"{container_name}:latest",
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": str(self.compose_project or "snowl"),
            "T_BENCH_CONTAINER_LOGS_PATH": "/var/log/tbench",
            "T_BENCH_CONTAINER_AGENT_LOGS_PATH": "/agent-logs",
            "T_BENCH_TEST_DIR": "/tests",
            "T_BENCH_TASK_LOGS_PATH": str(logs_dir),
            "T_BENCH_TASK_AGENT_LOGS_PATH": str(agent_logs_dir),
            "TEST_DIR": "/tests",
        }
        for key, value in defaults.items():
            current = self.compose_env.get(key)
            if current is None or not str(current).strip():
                self.compose_env[key] = value

    def _compose_base_cmd(self) -> list[str]:
        if not self.compose_file:
            raise RuntimeError("compose_file is required when use_docker_compose=True")
        return [
            "docker",
            "compose",
            "-p",
            str(self.compose_project),
            "-f",
            str(self.compose_file),
        ]

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = int(time.time() * 1000)
        command_text = " ".join(str(x) for x in cmd)

        def _emit(evt: dict[str, Any]) -> None:
            if on_event is None:
                return
            try:
                on_event(dict(evt))
            except Exception:
                return

        _emit({"event": "runtime.env.command.start", "command_text": command_text})
        proc = subprocess.Popen(
            cmd,
            cwd=self.workdir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            env=dict(env or os.environ),
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        q: Queue[tuple[str, str | None]] = Queue()

        def _reader(stream: Any, stream_name: str) -> None:
            try:
                if stream is None:
                    return
                for line in iter(stream.readline, ""):
                    q.put((stream_name, line))
            finally:
                try:
                    if stream is not None:
                        stream.close()
                finally:
                    q.put((stream_name, None))

        t_out = threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()
        done_streams = 0
        timed_out = False
        while done_streams < 2:
            if timeout_seconds is not None and (time.time() * 1000 - started) > timeout_seconds * 1000:
                timed_out = True
                proc.kill()
                _emit(
                    {
                        "event": "runtime.env.command.timeout",
                        "command_text": command_text,
                        "timeout_seconds": timeout_seconds,
                    }
                )
                break
            try:
                stream_name, chunk = q.get(timeout=0.1)
            except Empty:
                if proc.poll() is not None and done_streams >= 2:
                    break
                continue
            if chunk is None:
                done_streams += 1
                continue
            if stream_name == "stdout":
                stdout_parts.append(chunk)
            else:
                stderr_parts.append(chunk)
            _emit(
                {
                    "event": f"runtime.env.command.{stream_name}",
                    "command_text": command_text,
                    "chunk": chunk.rstrip("\n"),
                }
            )

        t_out.join(timeout=0.2)
        t_err.join(timeout=0.2)
        if timed_out:
            exit_code = -9
        else:
            exit_code = int(proc.wait())
        stdout_text = "".join(stdout_parts)
        stderr_text = "".join(stderr_parts)
        ended = int(time.time() * 1000)
        out = {
            "command": cmd,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": exit_code,
            "started_at_ms": started,
            "ended_at_ms": ended,
            "duration_ms": max(0, ended - started),
        }
        _emit(
            {
                "event": "runtime.env.command.finish",
                "command_text": command_text,
                "exit_code": exit_code,
                "duration_ms": out["duration_ms"],
            }
        )
        self._last_output = stdout_text + ((("\n" + stderr_text) if stderr_text else ""))
        self.history.append(out)
        return out

    def compose_up(
        self,
        *,
        build: bool | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not self.use_docker_compose:
            out = {"event": "terminal.compose.up", "skipped": True}
            self.history.append(out)
            return out
        base = self._compose_base_cmd()
        merged_env = {**os.environ, **self.compose_env}
        build_out: dict[str, Any] | None = None

        build_enabled = self.compose_build if build is None else bool(build)
        if build_enabled:
            with _BuildSemaphoreContext(_BUILD_LIMIT_SEMAPHORE):
                build_out = self._run_subprocess(
                    [*base, "build"],
                    timeout_seconds=1800.0,
                    env=merged_env,
                    on_event=on_event,
                )
            build_out["event"] = "terminal.compose.build"
            if build_out["exit_code"] != 0:
                return build_out

        up_out = self._run_subprocess(
            [*base, "up", "-d"],
            timeout_seconds=600.0,
            env=merged_env,
            on_event=on_event,
        )
        up_out["event"] = "terminal.compose.up"
        if build_out is not None:
            up_out["build"] = build_out
        self._compose_started = up_out.get("exit_code") == 0
        return up_out

    def compose_down(self, *, on_event: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        if not self.use_docker_compose:
            out = {"event": "terminal.compose.down", "skipped": True}
            self.history.append(out)
            return out
        base = self._compose_base_cmd()
        merged_env = {**os.environ, **self.compose_env}
        down_out = self._run_subprocess(
            [*base, "down"],
            timeout_seconds=120.0,
            env=merged_env,
            on_event=on_event,
        )
        down_out["event"] = "terminal.compose.down"
        self._compose_started = False
        return down_out

    def compose_exec(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
        service: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not self.use_docker_compose:
            return self.exec(command, timeout_seconds=timeout_seconds)

        if not self._compose_started:
            up_out = self.compose_up(on_event=on_event)
            if up_out.get("exit_code", 1) != 0:
                return up_out

        base = self._compose_base_cmd()
        target = service or self.compose_service or "client"
        cmd = [*base, "exec", "-T", target, "bash", "-lc", command]
        merged_env = {**os.environ, **self.compose_env}
        out = self._run_subprocess(cmd, timeout_seconds=timeout_seconds, env=merged_env, on_event=on_event)
        out["event"] = "terminal.compose.exec"
        out["service"] = target
        out["command_text"] = command
        return out

    def run_tests(
        self,
        *,
        timeout_seconds: float | None = None,
        run_tests_path: str | None = None,
    ) -> dict[str, Any]:
        if self.use_docker_compose:
            remote_run_script = "run-tests.sh"
            if run_tests_path:
                remote_run_script = Path(run_tests_path).name
            command = (
                "if [ -f /app/{name} ]; then bash /app/{name}; "
                "elif [ -f {name} ]; then bash {name}; "
                "elif [ -f /tests/run-tests.sh ]; then bash /tests/run-tests.sh; "
                "else echo 'run-tests.sh not found' && exit 1; fi"
            ).format(name=remote_run_script)
            out = self.compose_exec(command, timeout_seconds=timeout_seconds)
            out["event"] = "terminal.run_tests"
            return out
        if run_tests_path:
            rel = Path(run_tests_path).name
            out = self.exec(f"bash {rel}", timeout_seconds=timeout_seconds)
            out["event"] = "terminal.run_tests"
            return out
        out = self.exec("bash run-tests.sh", timeout_seconds=timeout_seconds)
        out["event"] = "terminal.run_tests"
        return out

    def exec(
        self,
        command: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self.use_docker_compose:
            return self.compose_exec(command, timeout_seconds=timeout_seconds)
        started = int(time.time() * 1000)
        proc = subprocess.run(
            command,
            shell=True,
            cwd=self.workdir,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        ended = int(time.time() * 1000)
        out = {
            "command": command,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": int(proc.returncode),
            "started_at_ms": started,
            "ended_at_ms": ended,
            "duration_ms": max(0, ended - started),
        }
        self._last_output = (proc.stdout or "") + ((("\n" + proc.stderr) if proc.stderr else ""))
        self.history.append(out)
        return out

    def send_keys(
        self,
        keystrokes: str,
        *,
        is_blocking: bool = False,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        # MVP semantics: treat keystrokes as shell command text when blocking.
        if is_blocking:
            return self.exec(keystrokes, timeout_seconds=timeout_sec)
        event = {"keystrokes": keystrokes, "is_blocking": False, "timeout_sec": timeout_sec}
        self.history.append(event)
        return event

    def capture(self) -> str:
        return self._last_output

    def wait(self, seconds: float) -> dict[str, Any]:
        started = int(time.time() * 1000)
        time.sleep(max(0.0, float(seconds)))
        ended = int(time.time() * 1000)
        evt = {"wait_seconds": float(seconds), "started_at_ms": started, "ended_at_ms": ended}
        self.history.append(evt)
        return evt
