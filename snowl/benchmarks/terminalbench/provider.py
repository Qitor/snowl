"""TerminalBench container provider — manages compose-based terminal containers.

Relocated from ``snowl.runtime.container_providers`` to resolve the
runtime → benchmark boundary violation.  The runtime layer no longer
imports this module directly; it is registered via
``register_container_provider`` during benchmark discovery.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Mapping

from snowl.core import EnvSpec
from snowl.envs import TerminalEnv
from snowl.runtime.container_providers import ContainerProviderContext, ContainerProvider, ContainerSession


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


def register_container_provider(registry: ContainerProviderRegistry) -> None:
    """Register the TerminalBench container provider with the given registry."""
    registry.register("terminalbench", TerminalBenchProvider())
