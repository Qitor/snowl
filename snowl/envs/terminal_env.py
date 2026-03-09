"""Terminal environment contract and local implementation."""

from __future__ import annotations

import os
import re
import shlex
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from snowl.core import EnvSpec, validate_env_spec
from snowl.envs.substrate import CommandRunner, ContainerBackend

_BUILD_LIMIT_LOCK = threading.Lock()
_BUILD_LIMIT_SEMAPHORE: threading.BoundedSemaphore | None = None
_BUILD_SLOT_CONTEXT_FACTORY: Callable[[], Any] | None = None


def set_compose_build_limit(limit: int | None) -> None:
    global _BUILD_LIMIT_SEMAPHORE
    with _BUILD_LIMIT_LOCK:
        if limit is None:
            _BUILD_LIMIT_SEMAPHORE = None
            return
        _BUILD_LIMIT_SEMAPHORE = threading.BoundedSemaphore(max(1, int(limit)))


def set_compose_build_slot_factory(factory: Callable[[], Any] | None) -> None:
    global _BUILD_SLOT_CONTEXT_FACTORY
    with _BUILD_LIMIT_LOCK:
        _BUILD_SLOT_CONTEXT_FACTORY = factory


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
    _TMUX_ENTER_KEYS = {"Enter", "C-m", "KPEnter", "C-j", "^M", "^J"}
    _TMUX_ENDS_WITH_NEWLINE_PATTERN = r"[\r\n]$"
    _TMUX_NEWLINE_CHARS = "\r\n"
    _TMUX_COMPLETION_SIGNAL = "done"
    _TMUX_COMPLETION_COMMAND = f"; tmux wait -S {_TMUX_COMPLETION_SIGNAL}"

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
    _tmux_session_name: str | None = None
    _tmux_session_ready: bool = False
    _command_runner: CommandRunner | None = field(default=None, init=False, repr=False)
    _container_backend: ContainerBackend | None = field(default=None, init=False, repr=False)

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
        if self._tmux_session_name is None:
            base = str(self.compose_project or Path(self.workdir).name or "snowl-terminal")
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-") or "snowl-terminal"
            self._tmux_session_name = f"{safe}-shell"
        self._command_runner = CommandRunner(cwd=self.workdir)
        self._container_backend = ContainerBackend(command_runner=self._command_runner)
        self._ensure_compose_env()

    def _build_slot_context(self):
        with _BUILD_LIMIT_LOCK:
            factory = _BUILD_SLOT_CONTEXT_FACTORY
            sem = _BUILD_LIMIT_SEMAPHORE
        if factory is not None:
            return factory()
        return _BuildSemaphoreContext(sem)

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

    def _compose_identity(self) -> tuple[str, str]:
        if not self.compose_file:
            raise RuntimeError("compose_file is required when use_docker_compose=True")
        return str(self.compose_project), str(self.compose_file)

    def _compose_exec_args(
        self,
        args: list[str],
        *,
        timeout_seconds: float | None = None,
        service: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return self.compose_exec(
            shlex.join(args),
            timeout_seconds=timeout_seconds,
            service=service,
            on_event=on_event,
        )

    @staticmethod
    def _exit_code(out: Mapping[str, Any]) -> int:
        raw = out.get("exit_code", 1)
        return 1 if raw is None else int(raw)

    def _tmux_has_session(self) -> bool:
        out = self._compose_exec_args(
            ["tmux", "has-session", "-t", str(self._tmux_session_name or "")],
            timeout_seconds=10.0,
        )
        return self._exit_code(out) == 0

    def _ensure_tmux_session(self) -> None:
        if not self.use_docker_compose:
            return
        if self._tmux_session_ready and self._tmux_has_session():
            return
        if self._tmux_has_session():
            self._tmux_session_ready = True
            return
        session = str(self._tmux_session_name or "snowl-terminal")
        command = (
            f"tmux new-session -x 160 -y 40 -d -s {session} \\; "
            f"set-option -t {session} history-limit 50000"
        )
        out = self.compose_exec(command, timeout_seconds=30.0)
        if self._exit_code(out) != 0:
            raise RuntimeError(
                "Failed to create tmux session: "
                + str((out.get("stderr") or out.get("stdout") or "").strip())
            )
        self._tmux_session_ready = True

    def _tmux_is_enter_key(self, key: str) -> bool:
        return key in self._TMUX_ENTER_KEYS

    def _tmux_ends_with_newline(self, key: str) -> bool:
        return re.search(self._TMUX_ENDS_WITH_NEWLINE_PATTERN, key) is not None

    def _tmux_is_executing_command(self, key: str) -> bool:
        return self._tmux_is_enter_key(key) or self._tmux_ends_with_newline(key)

    def _tmux_prevent_execution(self, keys: list[str]) -> list[str]:
        prepared = keys.copy()
        while prepared and self._tmux_is_executing_command(prepared[-1]):
            if self._tmux_is_enter_key(prepared[-1]):
                prepared.pop()
                continue
            stripped = prepared[-1].rstrip(self._TMUX_NEWLINE_CHARS)
            if stripped:
                prepared[-1] = stripped
            else:
                prepared.pop()
        return prepared

    def _tmux_prepare_keys(self, keys: str | list[str], *, block: bool) -> tuple[list[str], bool]:
        prepared = [keys] if isinstance(keys, str) else list(keys)
        if not block or not prepared or not self._tmux_is_executing_command(prepared[-1]):
            return prepared, False
        prepared = self._tmux_prevent_execution(prepared)
        prepared.extend([self._TMUX_COMPLETION_COMMAND, "Enter"])
        return prepared, True

    def _tmux_send_keys(self, keys: str | list[str], *, block: bool, timeout_seconds: float | None) -> dict[str, Any]:
        self._ensure_tmux_session()
        prepared_keys, is_blocking = self._tmux_prepare_keys(keys, block=block)
        send_out = self._compose_exec_args(
            ["tmux", "send-keys", "-t", str(self._tmux_session_name or ""), *prepared_keys],
            timeout_seconds=timeout_seconds,
        )
        if self._exit_code(send_out) != 0:
            raise RuntimeError(
                "Failed to send tmux keys: "
                + str((send_out.get("stderr") or send_out.get("stdout") or "").strip())
            )
        if not is_blocking:
            send_out["keystrokes"] = keys if isinstance(keys, str) else "".join(keys)
            send_out["is_blocking"] = False
            send_out["timeout_sec"] = timeout_seconds
            return send_out

        wait_timeout = float(timeout_seconds if timeout_seconds is not None else 180.0)
        wait_out = self._compose_exec_args(
            ["timeout", f"{wait_timeout}s", "tmux", "wait", self._TMUX_COMPLETION_SIGNAL],
            timeout_seconds=wait_timeout,
        )
        if self._exit_code(wait_out) != 0:
            raise TimeoutError(f"Command timed out after {wait_timeout} seconds")
        wait_out["keystrokes"] = keys if isinstance(keys, str) else "".join(keys)
        wait_out["is_blocking"] = True
        wait_out["timeout_sec"] = timeout_seconds
        return wait_out

    def _tmux_capture(self) -> str:
        self._ensure_tmux_session()
        out = self._compose_exec_args(
            ["tmux", "capture-pane", "-p", "-t", str(self._tmux_session_name or "")],
            timeout_seconds=10.0,
        )
        if self._exit_code(out) != 0:
            raise RuntimeError(
                "Failed to capture tmux pane: "
                + str((out.get("stderr") or out.get("stdout") or "").strip())
            )
        self._last_output = str(out.get("stdout") or "")
        return self._last_output

    def _run_process(
        self,
        cmd: list[str],
        *,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        out = (self._command_runner or CommandRunner(cwd=self.workdir)).run(
            cmd,
            timeout_seconds=timeout_seconds,
            env=env,
            on_event=on_event,
            cwd=self.workdir,
        )
        if bool(out.get("timed_out")):
            raise TimeoutError(f"Command timed out after {float(timeout_seconds or 0.0)} seconds")
        stdout_text = str(out.get("stdout") or "")
        stderr_text = str(out.get("stderr") or "")
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
        project, compose_file = self._compose_identity()
        backend = self._container_backend or ContainerBackend(
            command_runner=self._command_runner or CommandRunner(cwd=self.workdir)
        )
        merged_env = {**os.environ, **self.compose_env}
        build_out: dict[str, Any] | None = None

        build_enabled = self.compose_build if build is None else bool(build)
        if build_enabled:
            with self._build_slot_context():
                build_out = backend.compose_build(
                    project=project,
                    compose_file=compose_file,
                    timeout_seconds=1800.0,
                    env=merged_env,
                    on_event=on_event,
                )
                self.history.append(build_out)
            build_out["event"] = "terminal.compose.build"
            if build_out["exit_code"] != 0:
                return build_out

        up_out = backend.compose_up(
            project=project,
            compose_file=compose_file,
            timeout_seconds=600.0,
            env=merged_env,
            on_event=on_event,
        )
        self.history.append(up_out)
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
        project, compose_file = self._compose_identity()
        backend = self._container_backend or ContainerBackend(
            command_runner=self._command_runner or CommandRunner(cwd=self.workdir)
        )
        merged_env = {**os.environ, **self.compose_env}
        down_out = backend.compose_down(
            project=project,
            compose_file=compose_file,
            timeout_seconds=120.0,
            env=merged_env,
            on_event=on_event,
        )
        self.history.append(down_out)
        down_out["event"] = "terminal.compose.down"
        self._compose_started = False
        self._tmux_session_ready = False
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

        project, compose_file = self._compose_identity()
        backend = self._container_backend or ContainerBackend(
            command_runner=self._command_runner or CommandRunner(cwd=self.workdir)
        )
        target = service or self.compose_service or "client"
        merged_env = {**os.environ, **self.compose_env}
        out = backend.compose_exec(
            project=project,
            compose_file=compose_file,
            service=target,
            command=command,
            timeout_seconds=timeout_seconds,
            env=merged_env,
            on_event=on_event,
        )
        self.history.append(out)
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
        out = self._run_process(
            ["bash", "-lc", command],
            timeout_seconds=timeout_seconds,
        )
        out["command"] = command
        return out

    def send_keys(
        self,
        keystrokes: str,
        *,
        is_blocking: bool = False,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        if self.use_docker_compose:
            return self._tmux_send_keys(
                keystrokes,
                block=is_blocking,
                timeout_seconds=timeout_sec,
            )
        # MVP semantics: treat keystrokes as shell command text when blocking.
        if is_blocking:
            return self.exec(keystrokes, timeout_seconds=timeout_sec)
        event = {"keystrokes": keystrokes, "is_blocking": False, "timeout_sec": timeout_sec}
        self.history.append(event)
        return event

    def capture(self) -> str:
        if self.use_docker_compose:
            return self._tmux_capture()
        return self._last_output

    def wait(self, seconds: float) -> dict[str, Any]:
        started = int(time.time() * 1000)
        time.sleep(max(0.0, float(seconds)))
        ended = int(time.time() * 1000)
        evt = {"wait_seconds": float(seconds), "started_at_ms": started, "ended_at_ms": ended}
        self.history.append(evt)
        return evt
