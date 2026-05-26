"""Registry and concrete benchmark container providers (TerminalBench, OSWorld) used by runtime prepare/finalize paths.

Framework role:
- Maps benchmark metadata into concrete env/container startup commands, per-trial isolation identifiers, and close behavior.
- Computes trial-level `spec_hash` and requirement metadata consumed upstream.

Runtime/usage wiring:
- Provider selection happens through benchmark keys from task metadata.
- TerminalBench and OSWorld providers are the concrete bridge from shared runtime APIs to benchmark runtime realities.
- Key top-level symbols in this file: `ContainerSession`, `ContainerProviderContext`, `ContainerProvider`, `ContainerProviderRegistry`, `TerminalBenchProvider`, `OSWorldProvider` (lazy import).

Change guardrails:
- Keep benchmark-specific assumptions in this layer; do not leak them into global scheduler logic without contract changes.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from snowl.core import EnvSpec
from snowl.envs import GuiEnv, TerminalEnv
from snowl.envs.substrate import CommandRunner, ContainerBackend
from snowl.runtime.container_contract import RuntimeContainerSpec


@dataclass
class ContainerSession:
    kind: str
    env: Any
    benchmark: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContainerProviderContext:
    run_id: str | None
    trial_id: str | None
    task_id: str
    agent_id: str
    variant_id: str
    task_env_type: str
    task_metadata: Mapping[str, Any]
    sample: Mapping[str, Any]
    container_spec: RuntimeContainerSpec
    emit: Callable[[dict[str, Any]], None] | None = None

    def emit_event(self, event: dict[str, Any]) -> None:
        if self.emit is None:
            return
        payload = {
            "run_id": self.run_id,
            "trial_id": self.trial_id,
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

    async def prepare(self, context: ContainerProviderContext) -> ContainerSession: ...

    async def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None: ...

    def describe_requirements(self, context: ContainerProviderContext) -> dict[str, Any]: ...


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

    def describe_requirements(self, context: ContainerProviderContext) -> dict[str, Any]:
        startup = dict(context.container_spec.startup)
        compose_path = str(startup.get("compose_file") or "").strip()
        compose_build = bool(startup.get("compose_build", True))
        return {
            "benchmark": "terminalbench",
            "requires_container": bool(context.container_spec.requires_container),
            "requires_build": compose_build and bool(compose_path and Path(compose_path).exists()),
            "spec_hash": context.container_spec.spec_hash,
            "prepare_provider_ids": (),
            "estimated_prepare_cost": "heavy" if context.container_spec.requires_container else "none",
            "startup": startup,
        }

    async def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        startup = dict(context.container_spec.startup)
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(startup.get("safe_task") or "task")).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(startup.get("safe_sample") or "sample")).strip("-") or "sample"
        safe_variant = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(startup.get("safe_variant") or "default")).strip("-") or "default"
        trial_name = str(startup.get("compose_project") or f"snowl-tb-{safe_task}-{safe_sample[:12]}-{safe_variant[:12]}")
        workdir = startup.get("task_root") or str(Path.cwd())
        workdir_path = Path(str(workdir)).resolve()
        logs_root = Path(str(startup.get("task_logs_path") or (workdir_path / ".snowl_logs" / safe_sample / safe_variant))).resolve()
        agent_logs_root = Path(
            str(startup.get("task_agent_logs_path") or (workdir_path / ".snowl_agent_logs" / safe_sample / safe_variant))
        ).resolve()
        logs_root.mkdir(parents=True, exist_ok=True)
        agent_logs_root.mkdir(parents=True, exist_ok=True)
        docker_compose_path = str(startup.get("compose_file") or "").strip()
        use_compose = bool(docker_compose_path and Path(docker_compose_path).exists())
        compose_build = bool(startup.get("compose_build", True))
        compose_env = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": str(startup.get("client_container_name") or trial_name),
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": str(
                startup.get("client_image_name") or f"tb__{safe_task}__{safe_variant}__client"
            ),
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": str(startup.get("compose_name_prefix") or f"tb__{safe_task}__{safe_variant}"),
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
            compose_service=str(startup.get("compose_service") or "client"),
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
            up_out = await asyncio.to_thread(
                env.compose_up,
                on_event=lambda evt: context.emit_env_stream(
                    evt,
                    project=env.compose_project,
                    compose_file=env.compose_file,
                ),
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
            metadata={
                "project": env.compose_project,
                "compose_file": env.compose_file,
                "compose_service": env.compose_service,
                "spec_hash": self.describe_requirements(context).get("spec_hash"),
            },
        )

    async def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None:
        env = session.env
        project = getattr(env, "compose_project", None)
        context.emit_event({"event": "terminalbench.container.stopping", "phase": "env", "project": project})
        down_out = await asyncio.to_thread(
            env.compose_down,
            on_event=lambda evt: context.emit_env_stream(
                evt,
                project=project,
                compose_file=getattr(env, "compose_file", None),
            ),
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


class ComposeTerminalProvider:
    name = "compose_terminal"

    def describe_requirements(self, context: ContainerProviderContext) -> dict[str, Any]:
        startup = dict(context.container_spec.startup)
        compose_path = str(startup.get("compose_file") or "").strip()
        compose_build = bool(startup.get("compose_build", True))
        return {
            "benchmark": context.container_spec.benchmark,
            "provider_name": self.name,
            "requires_container": bool(context.container_spec.requires_container),
            "requires_build": compose_build and bool(compose_path and Path(compose_path).exists()),
            "spec_hash": context.container_spec.spec_hash,
            "prepare_provider_ids": (),
            "estimated_prepare_cost": "medium" if context.container_spec.requires_container else "none",
            "startup": startup,
        }

    async def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        startup = dict(context.container_spec.startup)
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(context.task_id or "task")).strip("-") or "task"
        safe_sample = re.sub(
            r"[^a-zA-Z0-9._-]+",
            "-",
            str((context.sample or {}).get("id") or "sample"),
        ).strip("-") or "sample"
        safe_variant = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(context.variant_id or "default")).strip("-") or "default"
        project = str(startup.get("compose_project") or f"snowl-ct-{safe_task}-{safe_sample[:12]}-{safe_variant[:12]}")
        workdir = Path(str(startup.get("workdir") or startup.get("task_root") or Path.cwd())).resolve()
        compose_file = str(startup.get("compose_file") or "").strip()
        use_compose = bool(compose_file and Path(compose_file).exists())
        workspace_dir = str(startup.get("workspace_dir") or context.container_spec.workspace.get("workspace_dir") or "").strip()
        compose_env = {str(k): str(v) for k, v in dict(startup.get("compose_env") or {}).items()}
        compose_env.update({str(k): str(v) for k, v in context.container_spec.env.items()})
        if workspace_dir:
            compose_env.setdefault("SNOWL_WORKSPACE", workspace_dir)
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
            workdir=str(workdir),
            compose_file=(compose_file if compose_file else None),
            use_docker_compose=use_compose,
            compose_build=bool(startup.get("compose_build", True)),
            compose_project=project,
            compose_service=str(startup.get("compose_service") or "client"),
            compose_env=compose_env,
        )
        if use_compose:
            docker_path = context.ensure_docker_available(benchmark=context.container_spec.benchmark or self.name)
            context.emit_event(
                {
                    "event": "compose_terminal.container.starting",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                    "service": env.compose_service,
                    "docker_path": docker_path,
                }
            )
            up_out = await asyncio.to_thread(
                env.compose_up,
                on_event=lambda evt: context.emit_env_stream(
                    evt,
                    project=env.compose_project,
                    compose_file=env.compose_file,
                ),
            )
            context.emit_event(
                {
                    "event": "compose_terminal.container.started",
                    "phase": "env",
                    "project": env.compose_project,
                    "exit_code": up_out.get("exit_code"),
                    "duration_ms": up_out.get("duration_ms"),
                }
            )
            if up_out.get("exit_code", 1) != 0:
                raise RuntimeError(
                    "compose_terminal docker compose up failed: "
                    + str((up_out.get("stderr") or up_out.get("stdout") or "").strip())
                )
            await self._run_lifecycle_command(context, env, "init", context.container_spec.init_command)
            await self._run_lifecycle_command(context, env, "start", context.container_spec.start_command)
        else:
            context.emit_event(
                {
                    "event": "compose_terminal.container.disabled",
                    "phase": "env",
                    "reason": "compose_file_not_found",
                    "compose_file": compose_file,
                }
            )
            await self._run_lifecycle_command(context, env, "init", context.container_spec.init_command)
            await self._run_lifecycle_command(context, env, "start", context.container_spec.start_command)
        return ContainerSession(
            kind="terminal_compose",
            env=env,
            benchmark=context.container_spec.benchmark or self.name,
            metadata={
                "project": env.compose_project,
                "compose_file": env.compose_file,
                "compose_service": env.compose_service,
                "workspace_dir": workspace_dir or None,
                "spec_hash": self.describe_requirements(context).get("spec_hash"),
            },
        )

    async def _run_lifecycle_command(
        self,
        context: ContainerProviderContext,
        env: TerminalEnv,
        label: str,
        command: str | None,
    ) -> dict[str, Any] | None:
        if not command:
            return None
        context.emit_event({"event": f"compose_terminal.container.{label}.start", "phase": "env", "command_text": command})
        out = await asyncio.to_thread(
            env.exec,
            command,
            timeout_seconds=float(context.container_spec.resource_limits.get(f"{label}_timeout_seconds", 120.0)),
        )
        context.emit_event(
            {
                "event": f"compose_terminal.container.{label}.finish",
                "phase": "env",
                "command_text": command,
                "exit_code": out.get("exit_code"),
                "duration_ms": out.get("duration_ms"),
                "stdout_tail": str(out.get("stdout", ""))[-240:],
                "stderr_tail": str(out.get("stderr", ""))[-240:],
            }
        )
        if out.get("exit_code", 1) != 0:
            raise RuntimeError(f"compose_terminal {label}_command failed: {out.get('stderr') or out.get('stdout') or ''}")
        return out

    async def close(self, context: ContainerProviderContext, session: ContainerSession) -> dict[str, Any] | None:
        env = session.env
        check_out = await self._run_lifecycle_command(context, env, "check", context.container_spec.check_command)
        if not getattr(env, "use_docker_compose", False):
            return check_out
        project = getattr(env, "compose_project", None)
        context.emit_event({"event": "compose_terminal.container.stopping", "phase": "env", "project": project})
        down_out = await asyncio.to_thread(
            env.compose_down,
            on_event=lambda evt: context.emit_env_stream(
                evt,
                project=project,
                compose_file=getattr(env, "compose_file", None),
            ),
        )
        context.emit_event(
            {
                "event": "compose_terminal.container.stopped",
                "phase": "env",
                "project": project,
                "exit_code": down_out.get("exit_code"),
            }
        )
        if check_out is not None:
            down_out["check"] = check_out
        return down_out


class DockerContainerProvider:
    name = "docker_container"

    def describe_requirements(self, context: ContainerProviderContext) -> dict[str, Any]:
        startup = dict(context.container_spec.startup)
        return {
            "benchmark": context.container_spec.benchmark,
            "provider_name": self.name,
            "requires_container": bool(context.container_spec.requires_container),
            "requires_build": False,
            "spec_hash": context.container_spec.spec_hash,
            "prepare_provider_ids": (),
            "estimated_prepare_cost": "medium",
            "startup": startup,
        }

    async def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        startup = dict(context.container_spec.startup)
        image = str(startup.get("image") or startup.get("docker_image") or "").strip()
        if not image:
            raise RuntimeError("docker_container provider requires startup.image.")
        docker_path = context.ensure_docker_available(benchmark=context.container_spec.benchmark or self.name)
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(context.task_id or "task")).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", str((context.sample or {}).get("id") or "sample")).strip("-") or "sample"
        safe_variant = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(context.variant_id or "default")).strip("-") or "default"
        container_name = str(startup.get("container_name") or f"snowl-dc-{safe_task}-{safe_sample[:12]}-{safe_variant[:12]}")
        workspace_dir = str(startup.get("workspace_dir") or context.container_spec.workspace.get("workspace_dir") or "").strip()
        volumes = {str(workspace_dir): str(startup.get("workspace_mount") or "/workspace")} if workspace_dir else {}
        volumes.update({str(k): str(v) for k, v in dict(startup.get("volumes") or {}).items()})
        env_vars = {**context.container_spec.env, **{str(k): str(v) for k, v in dict(startup.get("env") or {}).items()}}
        if workspace_dir:
            env_vars.setdefault("SNOWL_WORKSPACE", str(startup.get("workspace_mount") or "/workspace"))
        runner = CommandRunner(cwd=workspace_dir or None)
        backend = ContainerBackend(command_runner=runner)
        context.emit_event(
            {
                "event": "docker_container.container.starting",
                "phase": "env",
                "image": image,
                "container_name": container_name,
                "docker_path": docker_path,
                "network": context.container_spec.network,
                "workspace_dir": workspace_dir or None,
            }
        )
        out = await asyncio.to_thread(
            backend.run,
            image=image,
            name=container_name,
            command=str(startup.get("command") or "sleep infinity"),
            workdir=str(startup.get("workdir") or (startup.get("workspace_mount") or "/workspace")),
            network=context.container_spec.network,
            env=env_vars,
            volumes=volumes,
            detach=True,
            timeout_seconds=float(context.container_spec.resource_limits.get("start_timeout_seconds", 120.0)),
            on_event=context.emit_env_stream,
        )
        container_id = str(out.get("stdout") or "").strip().splitlines()[-1] if str(out.get("stdout") or "").strip() else container_name
        context.emit_event(
            {
                "event": "docker_container.container.started",
                "phase": "env",
                "container_id": container_id,
                "container_name": container_name,
                "exit_code": out.get("exit_code"),
                "duration_ms": out.get("duration_ms"),
            }
        )
        if out.get("exit_code", 1) != 0:
            raise RuntimeError("docker_container docker run failed: " + str((out.get("stderr") or out.get("stdout") or "").strip()))
        await self._run_docker_lifecycle_command(context, backend, container_id, "init", context.container_spec.init_command)
        await self._run_docker_lifecycle_command(context, backend, container_id, "start", context.container_spec.start_command)
        return ContainerSession(
            kind="docker_container",
            env={
                "container_id": container_id,
                "container_name": container_name,
                "workspace_dir": workspace_dir or None,
                "backend": backend,
            },
            benchmark=context.container_spec.benchmark or self.name,
            metadata={
                "container_id": container_id,
                "container_name": container_name,
                "workspace_dir": workspace_dir or None,
                "image": image,
                "spec_hash": self.describe_requirements(context).get("spec_hash"),
            },
        )

    async def _run_docker_lifecycle_command(
        self,
        context: ContainerProviderContext,
        backend: ContainerBackend,
        container_id: str,
        label: str,
        command: str | None,
    ) -> dict[str, Any] | None:
        if not command:
            return None
        mount = str(context.container_spec.startup.get("workspace_mount") or "/workspace")
        context.emit_event({"event": f"docker_container.container.{label}.start", "phase": "env", "command_text": command})
        out = await asyncio.to_thread(
            backend.exec,
            container_id,
            command,
            workdir=mount,
            env=context.container_spec.env,
            timeout_seconds=float(context.container_spec.resource_limits.get(f"{label}_timeout_seconds", 120.0)),
            on_event=context.emit_env_stream,
        )
        context.emit_event(
            {
                "event": f"docker_container.container.{label}.finish",
                "phase": "env",
                "command_text": command,
                "exit_code": out.get("exit_code"),
                "duration_ms": out.get("duration_ms"),
                "stdout_tail": str(out.get("stdout", ""))[-240:],
                "stderr_tail": str(out.get("stderr", ""))[-240:],
            }
        )
        if out.get("exit_code", 1) != 0:
            raise RuntimeError(f"docker_container {label}_command failed: {out.get('stderr') or out.get('stdout') or ''}")
        return out

    async def close(self, context: ContainerProviderContext, session: ContainerSession) -> dict[str, Any] | None:
        env = dict(session.env or {})
        backend: ContainerBackend = env["backend"]
        container_id = str(env.get("container_id") or env.get("container_name") or "")
        check_out = await self._run_docker_lifecycle_command(context, backend, container_id, "check", context.container_spec.check_command)
        context.emit_event({"event": "docker_container.container.stopping", "phase": "env", "container_id": container_id})
        out = await asyncio.to_thread(
            backend.rm,
            container_id,
            force=True,
            timeout_seconds=float(context.container_spec.resource_limits.get("stop_timeout_seconds", 60.0)),
            on_event=context.emit_env_stream,
        )
        context.emit_event(
            {
                "event": "docker_container.container.stopped",
                "phase": "env",
                "container_id": container_id,
                "exit_code": out.get("exit_code"),
            }
        )
        if check_out is not None:
            out["check"] = check_out
        return out


class OSWorldProvider:
    name = "osworld"

    def describe_requirements(self, context: ContainerProviderContext) -> dict[str, Any]:
        return {
            "benchmark": "osworld",
            "requires_container": bool(context.container_spec.requires_container),
            "requires_build": False,
            "spec_hash": context.container_spec.spec_hash,
            "prepare_provider_ids": (),
            "estimated_prepare_cost": "heavy",
            "startup": dict(context.container_spec.startup),
        }

    async def prepare(self, context: ContainerProviderContext) -> ContainerSession:
        from snowl.benchmarks.osworld.container import OSWorldContainerLauncher

        docker_path = context.ensure_docker_available(benchmark="osworld")
        launcher = OSWorldContainerLauncher(
            repo_root=Path(__file__).resolve().parents[2],
            emit=context.emit_event,
            settings=context.container_spec.startup,
        )
        prepared = await asyncio.to_thread(launcher.prepare, docker_path=docker_path)
        return ContainerSession(
            kind="gui_container",
            env=prepared.env,
            benchmark="osworld",
            metadata={
                **dict(prepared.metadata),
                "spec_hash": self.describe_requirements(context).get("spec_hash"),
            },
        )

    async def close(
        self,
        context: ContainerProviderContext,
        session: ContainerSession,
    ) -> dict[str, Any] | None:
        env: GuiEnv = session.env
        context.emit_event({"event": "osworld.container.stopping", "phase": "env"})
        stop_evt = await asyncio.to_thread(
            env.stop_container,
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
        # Built-in providers
        registry.register("terminalbench", TerminalBenchProvider())
        registry.register("osworld", OSWorldProvider())
        registry.register("compose_terminal", ComposeTerminalProvider())
        registry.register("docker_container", DockerContainerProvider())
        # Discover plugin providers via entry_points
        _discover_plugin_providers(registry)
        _DEFAULT_PROVIDER_REGISTRY = registry
    return _DEFAULT_PROVIDER_REGISTRY


def _discover_plugin_providers(registry: ContainerProviderRegistry) -> None:
    """Discover ContainerProvider plugins from the ``snowl.container_providers`` entry point group."""
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return

    try:
        eps = entry_points(group="snowl.container_providers")
    except Exception:
        return

    for ep in eps:
        try:
            provider_cls = ep.load()
            provider = provider_cls()
            if hasattr(provider, "name"):
                registry.register(ep.name, provider)
        except Exception:
            pass
