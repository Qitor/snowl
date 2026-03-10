"""Provider registry for benchmark-specific container lifecycle."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from snowl.benchmarks.osworld.container import OSWorldContainerLauncher
from snowl.core import EnvSpec
from snowl.envs import GuiEnv, TerminalEnv


@dataclass
class ContainerSession:
    kind: str
    env: Any
    benchmark: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContainerProviderContext:
    task_id: str
    agent_id: str
    variant_id: str
    task_env_type: str
    task_metadata: Mapping[str, Any]
    sample: Mapping[str, Any]
    emit: Callable[[dict[str, Any]], None] | None = None

    def emit_event(self, event: dict[str, Any]) -> None:
        if self.emit is None:
            return
        payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "variant_id": self.variant_id,
            **dict(event),
        }
        try:
            self.emit(payload)
        except Exception:
            return

    def emit_env_stream(
        self,
        event: dict[str, Any],
        *,
        project: str | None = None,
        compose_file: str | None = None,
    ) -> None:
        payload = dict(event)
        payload.setdefault("phase", "env")
        if project:
            payload.setdefault("project", project)
        if compose_file:
            payload.setdefault("compose_file", compose_file)
        self.emit_event(payload)

    def ensure_docker_available(self, *, benchmark: str) -> str:
        docker_path = shutil.which("docker")
        if docker_path:
            return docker_path
        msg = (
            "docker executable not found in PATH. Install/start Docker Desktop and ensure "
            "'docker' is available in the current shell before running "
            f"{benchmark}."
        )
        self.emit_event(
            {
                "event": "runtime.env.preflight.error",
                "phase": "env",
                "code": "docker_not_found",
                "benchmark": benchmark,
                "message": msg,
            }
        )
        raise RuntimeError(msg)


class ContainerProvider(Protocol):
    name: str

    def prepare(self, context: ContainerProviderContext) -> ContainerSession: ...

    def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None: ...


class ContainerProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ContainerProvider] = {}

    def register(self, benchmark: str, provider: ContainerProvider) -> None:
        key = str(benchmark or "").strip().lower()
        if not key:
            raise ValueError("benchmark key is required")
        self._providers[key] = provider

    def resolve(self, benchmark: str) -> ContainerProvider | None:
        key = str(benchmark or "").strip().lower()
        if not key:
            return None
        return self._providers.get(key)


class TerminalBenchProvider:
    name = "terminalbench"

    def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        sample_meta = dict(context.sample.get("metadata", {}) or {})
        task_id = str(sample_meta.get("task_id") or "task")
        sample_id = str(context.sample.get("id") or "sample")
        variant_id = str(context.variant_id or "default")
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", sample_id).strip("-") or "sample"
        safe_variant = re.sub(r"[^a-zA-Z0-9._-]+", "-", variant_id).strip("-") or "default"
        trial_name = f"snowl-tb-{safe_task}-{safe_sample[:12]}-{safe_variant[:12]}"
        workdir = sample_meta.get("task_root") or str(Path.cwd())
        workdir_path = Path(str(workdir)).resolve()
        logs_root = workdir_path / ".snowl_logs" / safe_sample / safe_variant
        agent_logs_root = workdir_path / ".snowl_agent_logs" / safe_sample / safe_variant
        logs_root.mkdir(parents=True, exist_ok=True)
        agent_logs_root.mkdir(parents=True, exist_ok=True)
        docker_compose_path = str(sample_meta.get("docker_compose_path") or "").strip()
        use_compose = bool(docker_compose_path and Path(docker_compose_path).exists())
        compose_build = os.getenv("SNOWL_TB_COMPOSE_BUILD", "1") == "1"
        compose_env = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": trial_name,
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": f"tb__{safe_task}__{safe_variant}__client",
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": f"tb__{safe_task}__{safe_variant}",
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
            docker_path = context.ensure_docker_available(benchmark="terminalbench")
            context.emit_event(
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
            context.emit_event(
                {
                    "event": "terminalbench.container.starting",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                }
            )
            up_out = env.compose_up(
                on_event=lambda evt: context.emit_env_stream(
                    evt,
                    project=env.compose_project,
                    compose_file=env.compose_file,
                )
            )
            build_out = up_out.get("build")
            if isinstance(build_out, Mapping):
                context.emit_event(
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
            context.emit_event(
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
            context.emit_event(
                {
                    "event": "terminalbench.container.disabled",
                    "phase": "env",
                    "reason": "compose_file_not_found",
                    "docker_compose_path": docker_compose_path,
                }
            )

        return ContainerSession(
            kind="terminal_compose",
            env=env,
            benchmark="terminalbench",
            metadata={"project": env.compose_project},
        )

    def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None:
        env = session.env
        project = getattr(env, "compose_project", None)
        context.emit_event({"event": "terminalbench.container.stopping", "phase": "env", "project": project})
        down_out = env.compose_down(
            on_event=lambda evt: context.emit_env_stream(
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
        context.emit_event(payload)
        return down_out


class OSWorldProvider:
    name = "osworld"

    def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        docker_path = context.ensure_docker_available(benchmark="osworld")
        launcher = OSWorldContainerLauncher(
            repo_root=Path(__file__).resolve().parents[2],
            emit=context.emit_event,
        )
        prepared = launcher.prepare(docker_path=docker_path)
        return ContainerSession(
            kind="gui_container",
            env=prepared.env,
            benchmark="osworld",
            metadata=dict(prepared.metadata),
        )

    def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None:
        env: GuiEnv = session.env
        context.emit_event({"event": "osworld.container.stopping", "phase": "env"})
        stop_evt = env.stop_container(
            on_event=lambda evt: context.emit_env_stream(evt),
        )
        context.emit_event(
            {
                "event": "osworld.container.stopped",
                "phase": "env",
                "exit_code": stop_evt.get("exit_code"),
            }
        )
        return stop_evt


_DEFAULT_PROVIDER_REGISTRY: ContainerProviderRegistry | None = None


def default_container_provider_registry() -> ContainerProviderRegistry:
    global _DEFAULT_PROVIDER_REGISTRY
    if _DEFAULT_PROVIDER_REGISTRY is None:
        registry = ContainerProviderRegistry()
        registry.register("terminalbench", TerminalBenchProvider())
        registry.register("osworld", OSWorldProvider())
        _DEFAULT_PROVIDER_REGISTRY = registry
    return _DEFAULT_PROVIDER_REGISTRY
