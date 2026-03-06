"""Common container runtime orchestration for benchmark agents."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from snowl.benchmarks.osworld.container import OSWorldContainerLauncher
from snowl.core import EnvSpec
from snowl.envs import GuiEnv, TerminalEnv


@dataclass
class ContainerSession:
    kind: str
    env: Any
    benchmark: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ContainerRuntime:
    def __init__(
        self,
        *,
        task_id: str,
        agent_id: str,
        variant_id: str,
        task_env_type: str,
        task_metadata: Mapping[str, Any],
        sample: Mapping[str, Any],
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.task_id = task_id
        self.agent_id = agent_id
        self.variant_id = variant_id
        self.task_env_type = task_env_type
        self.task_metadata = dict(task_metadata or {})
        self.sample = dict(sample or {})
        self._emit = emit if callable(emit) else None
        self._session: ContainerSession | None = None

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._emit is None:
            return
        payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "variant_id": self.variant_id,
            **dict(event),
        }
        try:
            self._emit(payload)
        except Exception:
            return

    def _emit_env_stream(self, event: dict[str, Any], *, project: str | None = None, compose_file: str | None = None) -> None:
        payload = dict(event)
        payload.setdefault("phase", "env")
        if project:
            payload.setdefault("project", project)
        if compose_file:
            payload.setdefault("compose_file", compose_file)
        self._emit_event(payload)

    def _ensure_docker_available(self, *, benchmark: str) -> str:
        docker_path = shutil.which("docker")
        if docker_path:
            return docker_path
        msg = (
            "docker executable not found in PATH. Install/start Docker Desktop and ensure "
            "'docker' is available in the current shell before running "
            f"{benchmark}."
        )
        self._emit_event(
            {
                "event": "runtime.env.preflight.error",
                "phase": "env",
                "code": "docker_not_found",
                "benchmark": benchmark,
                "message": msg,
            }
        )
        raise RuntimeError(msg)

    def prepare(self) -> ContainerSession | None:
        benchmark = str(self.task_metadata.get("benchmark") or "").strip().lower()
        if benchmark == "terminalbench":
            self._session = self._prepare_terminalbench()
            return self._session
        if benchmark == "osworld":
            self._session = self._prepare_osworld()
            return self._session
        return None

    def close(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        session = self._session
        self._session = None
        env = session.env
        if session.kind == "terminal_compose":
            project = getattr(env, "compose_project", None)
            self._emit_event({"event": "terminalbench.container.stopping", "phase": "env", "project": project})
            down_out = env.compose_down(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=project,
                    compose_file=getattr(env, "compose_file", None),
                )
            )
            payload = {"event": "terminalbench.container.stopped", "phase": "env", "project": project}
            payload.update(
                {
                    "exit_code": down_out.get("exit_code"),
                    "duration_ms": down_out.get("duration_ms"),
                    "command_text": " ".join(down_out.get("command", []))
                    if isinstance(down_out.get("command"), list)
                    else down_out.get("command"),
                    "stdout_tail": str(down_out.get("stdout", ""))[-240:],
                    "stderr_tail": str(down_out.get("stderr", ""))[-240:],
                }
            )
            self._emit_event(payload)
            return down_out
        if session.kind == "gui_container":
            self._emit_event({"event": "osworld.container.stopping", "phase": "env"})
            stop_evt = env.stop_container(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=None,
                    compose_file=None,
                )
            )
            self._emit_event(
                {
                    "event": "osworld.container.stopped",
                    "phase": "env",
                    "exit_code": stop_evt.get("exit_code"),
                }
            )
            return stop_evt
        return None

    def _prepare_terminalbench(self) -> ContainerSession:
        sample_meta = dict(self.sample.get("metadata", {}) or {})
        task_id = str(sample_meta.get("task_id") or "task")
        sample_id = str(self.sample.get("id") or "sample")
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", sample_id).strip("-") or "sample"
        trial_name = f"snowl-tb-{safe_task}-{safe_sample[:16]}"
        workdir = sample_meta.get("task_root") or str(Path.cwd())
        workdir_path = Path(str(workdir)).resolve()
        logs_root = workdir_path / ".snowl_logs" / safe_sample
        agent_logs_root = workdir_path / ".snowl_agent_logs" / safe_sample
        logs_root.mkdir(parents=True, exist_ok=True)
        agent_logs_root.mkdir(parents=True, exist_ok=True)
        docker_compose_path = str(sample_meta.get("docker_compose_path") or "").strip()
        use_compose = bool(docker_compose_path and Path(docker_compose_path).exists())
        compose_build = os.getenv("SNOWL_TB_COMPOSE_BUILD", "1") == "1"
        compose_env = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": trial_name,
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": f"tb__{safe_task}__client",
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": f"tb__{safe_task}",
            "T_BENCH_CONTAINER_LOGS_PATH": "/var/log/tbench",
            "T_BENCH_CONTAINER_AGENT_LOGS_PATH": "/agent-logs",
            "T_BENCH_TEST_DIR": "/tests",
            "T_BENCH_TASK_LOGS_PATH": str(logs_root),
            "T_BENCH_TASK_AGENT_LOGS_PATH": str(agent_logs_root),
            "TEST_DIR": "/tests",
        }
        env = TerminalEnv(
            env_spec=EnvSpec(
                env_type="terminal",
                provided_ops=(
                    "process.run",
                    "terminal.exec",
                    "terminal.send_keys",
                    "terminal.capture",
                    "terminal.wait",
                ),
            ),
            workdir=str(workdir_path),
            compose_file=(docker_compose_path if docker_compose_path else None),
            use_docker_compose=use_compose,
            compose_build=compose_build,
            compose_project=trial_name,
            compose_service=str(sample_meta.get("compose_service", "client")),
            compose_env=compose_env,
        )
        if env.use_docker_compose:
            docker_path = self._ensure_docker_available(benchmark="terminalbench")
            self._emit_event(
                {
                    "event": "terminalbench.container.config",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                    "service": env.compose_service,
                    "docker_path": docker_path,
                    "compose_build": env.compose_build,
                    "env_injected": {
                        "client_container": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME"),
                        "client_image": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME"),
                        "test_dir": env.compose_env.get("T_BENCH_TEST_DIR"),
                        "task_logs": env.compose_env.get("T_BENCH_TASK_LOGS_PATH"),
                        "agent_logs": env.compose_env.get("T_BENCH_TASK_AGENT_LOGS_PATH"),
                    },
                }
            )
            self._emit_event(
                {
                    "event": "terminalbench.container.starting",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                }
            )
            up_out = env.compose_up(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=env.compose_project,
                    compose_file=env.compose_file,
                )
            )
            build_out = up_out.get("build")
            if isinstance(build_out, Mapping):
                self._emit_event(
                    {
                        "event": "terminalbench.container.build",
                        "phase": "env",
                        "project": env.compose_project,
                        "exit_code": build_out.get("exit_code"),
                        "duration_ms": build_out.get("duration_ms"),
                        "command_text": " ".join(build_out.get("command", []))
                        if isinstance(build_out.get("command"), list)
                        else build_out.get("command"),
                        "stdout_tail": str(build_out.get("stdout", ""))[-240:],
                        "stderr_tail": str(build_out.get("stderr", ""))[-240:],
                    }
                )
            self._emit_event(
                {
                    "event": "terminalbench.container.started",
                    "phase": "env",
                    "project": env.compose_project,
                    "exit_code": up_out.get("exit_code"),
                    "duration_ms": up_out.get("duration_ms"),
                    "command_text": " ".join(up_out.get("command", []))
                    if isinstance(up_out.get("command"), list)
                    else up_out.get("command"),
                    "stdout_tail": str(up_out.get("stdout", ""))[-240:],
                    "stderr_tail": str(up_out.get("stderr", ""))[-240:],
                }
            )
            if up_out.get("exit_code", 1) != 0:
                raise RuntimeError(
                    "terminalbench docker compose up failed: "
                    + str((up_out.get("stderr") or up_out.get("stdout") or "").strip())
                )
        else:
            self._emit_event(
                {
                    "event": "terminalbench.container.disabled",
                    "phase": "env",
                    "reason": "compose_file_not_found",
                    "docker_compose_path": docker_compose_path,
                }
            )
        return ContainerSession(kind="terminal_compose", env=env, benchmark="terminalbench", metadata={"project": env.compose_project})

    def _prepare_osworld(self) -> ContainerSession:
        docker_path = self._ensure_docker_available(benchmark="osworld")
        launcher = OSWorldContainerLauncher(
            repo_root=Path(__file__).resolve().parents[2],
            emit=self._emit_event,
        )
        prepared = launcher.prepare(docker_path=docker_path)
        return ContainerSession(
            kind="gui_container",
            env=prepared.env,
            benchmark="osworld",
            metadata=dict(prepared.metadata),
        )
