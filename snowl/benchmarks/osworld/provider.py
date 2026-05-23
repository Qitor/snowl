"""OSWorld container provider — manages GUI desktop containers for OSWorld tasks.

Relocated from ``snowl.runtime.container_providers`` to resolve the
runtime → benchmark boundary violation (H1).  The runtime layer no longer
imports this module directly; it is registered via
``register_container_provider`` during benchmark discovery.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from snowl.benchmarks.osworld.container import OSWorldContainerLauncher
from snowl.envs import GuiEnv
from snowl.runtime.container_providers import ContainerProviderContext, ContainerProvider, ContainerSession


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


def register_container_provider(registry: ContainerProviderRegistry) -> None:
    """Register the OSWorld container provider with the given registry."""
    registry.register("osworld", OSWorldProvider())
