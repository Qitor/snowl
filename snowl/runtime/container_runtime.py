"""Shared wrapper that translates a trial into benchmark-specific container provider prepare/finalize lifecycle calls.

Framework role:
- Decouples benchmark container setup details from the generic trial engine.
- Normalizes prepare metadata (`requires_container`, `requires_build`, `spec_hash`, provider ids) for upstream runtime logic.

Runtime/usage wiring:
- Delegates concrete behavior to registry-backed providers in `snowl.runtime.container_providers`.
- Used from trial prepare/finalize paths in runtime engine.
- Key top-level symbols in this file: `ContainerPrepareResult`, `ContainerRuntime`, `_run_sync`.

Change guardrails:
- Keep provider-agnostic contract stable; benchmark quirks belong in provider implementations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from snowl.runtime.container_contract import RuntimeContainerSpec, resolve_runtime_container_spec
from snowl.runtime.container_lifecycle import RuntimeContainerLifecycleManager
from snowl.runtime.container_providers import (
    ContainerProvider,
    ContainerProviderContext,
    ContainerProviderRegistry,
    ContainerSession,
    default_container_provider_registry,
)


@dataclass(frozen=True)
class ContainerPrepareResult:
    session: ContainerSession | None
    requires_container: bool
    requires_build: bool
    spec_hash: str | None = None
    prepare_provider_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    resource_id: str | None = None
    container_spec: RuntimeContainerSpec | None = None


class ContainerRuntime:
    def __init__(
        self,
        *,
        run_id: str | None = None,
        trial_id: str | None = None,
        task_id: str,
        agent_id: str,
        variant_id: str,
        task_env_type: str,
        task_metadata: Mapping[str, Any],
        sample: Mapping[str, Any],
        emit: Callable[[dict[str, Any]], None] | None = None,
        lifecycle_manager: RuntimeContainerLifecycleManager | None = None,
        provider_registry: ContainerProviderRegistry | None = None,
    ) -> None:
        self.run_id = run_id
        self.trial_id = trial_id
        self.task_id = task_id
        self.agent_id = agent_id
        self.variant_id = variant_id
        self.task_env_type = task_env_type
        self.task_metadata = dict(task_metadata or {})
        self.sample = dict(sample or {})
        self._emit = emit if callable(emit) else None
        self._lifecycle_manager = lifecycle_manager
        self._provider_registry = provider_registry or default_container_provider_registry()
        self._provider: ContainerProvider | None = None
        self._session: ContainerSession | None = None
        self._container_spec = resolve_runtime_container_spec(
            task_metadata=self.task_metadata,
            sample=self.sample,
        )
        self._resource_id: str | None = None

    def _context(self) -> ContainerProviderContext:
        return ContainerProviderContext(
            run_id=self.run_id,
            trial_id=self.trial_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            variant_id=self.variant_id,
            task_env_type=self.task_env_type,
            task_metadata=self.task_metadata,
            sample=self.sample,
            container_spec=self._container_spec,
            emit=self._emit,
        )

    def _resolve_provider(self) -> tuple[str, ContainerProvider | None]:
        benchmark = str(self._container_spec.benchmark or self.task_metadata.get("benchmark") or "").strip().lower()
        provider_name = str(self._container_spec.provider_name or "").strip().lower()
        provider = self._provider_registry.resolve(provider_name) if provider_name else None
        if provider is None:
            provider = self._provider_registry.resolve(benchmark)
        return (provider_name or benchmark), provider

    def describe_requirements(self) -> dict[str, Any]:
        benchmark, provider = self._resolve_provider()
        if provider is None and self._container_spec.requires_container:
            raise RuntimeError(
                f"Task declares runtime-managed container for benchmark='{benchmark}', "
                "but no container provider is registered."
            )
        if provider is None or not self._container_spec.requires_container:
            return {
                "benchmark": benchmark,
                "requires_container": False,
                "requires_build": False,
                "spec_hash": None,
                "prepare_provider_ids": (),
                "container_contract": self._container_spec.to_metadata(),
            }
        return dict(provider.describe_requirements(self._context()))

    async def prepare_phase(self) -> ContainerPrepareResult:
        benchmark, provider = self._resolve_provider()
        if provider is None and self._container_spec.requires_container:
            raise RuntimeError(
                f"Task declares runtime-managed container for benchmark='{benchmark}', "
                "but no container provider is registered."
            )
        if provider is None or not self._container_spec.requires_container:
            return ContainerPrepareResult(
                session=None,
                requires_container=False,
                requires_build=False,
                spec_hash=None,
                prepare_provider_ids=(),
                metadata={
                    "benchmark": benchmark,
                    "container_contract": self._container_spec.to_metadata(),
                },
                container_spec=self._container_spec,
            )
        context = self._context()
        self._provider = provider
        requirements = dict(provider.describe_requirements(context))
        self._session = await provider.prepare(context)
        resource_id: str | None = None
        if self._lifecycle_manager is not None and self._session is not None:
            env = self._session.env
            env_map = dict(env) if isinstance(env, Mapping) else {}
            resource_id = self._lifecycle_manager.register_container(
                trial_id=self.trial_id,
                benchmark=benchmark,
                provider_name=getattr(provider, "name", benchmark),
                spec_hash=self._container_spec.spec_hash,
                cleanup_policy=self._container_spec.cleanup_policy,
                debug_preserve=self._container_spec.debug_preserve_default,
                container_id=getattr(env, "container_id", None) or env_map.get("container_id"),
                compose_project=getattr(env, "compose_project", None) or env_map.get("compose_project"),
                compose_file=getattr(env, "compose_file", None) or env_map.get("compose_file"),
                workspace_dir=dict(self._session.metadata).get("workspace_dir"),
                session_kind=getattr(self._session, "kind", None),
                provider_metadata={
                    **dict(self._session.metadata),
                    "container_contract": self._container_spec.to_metadata(),
                },
                teardown=self._close_registered_session,
            )
            self._resource_id = resource_id
            self._lifecycle_manager.lease_resource(resource_id, trial_id=self.trial_id)
        return ContainerPrepareResult(
            session=self._session,
            requires_container=bool(requirements.get("requires_container", True)),
            requires_build=bool(requirements.get("requires_build", False)),
            spec_hash=(str(requirements.get("spec_hash")) if requirements.get("spec_hash") else None),
            prepare_provider_ids=tuple(str(x) for x in (requirements.get("prepare_provider_ids") or ()) if str(x).strip()),
            metadata={**requirements, "container_contract": self._container_spec.to_metadata()},
            resource_id=resource_id,
            container_spec=self._container_spec,
        )

    async def _close_registered_session(self) -> dict[str, Any] | None:
        if self._session is None or self._provider is None:
            return None
        session = self._session
        provider = self._provider
        self._session = None
        self._provider = None
        return await provider.close(self._context(), session)

    async def finalize_phase(self, *, outcome_status: str | None = None) -> dict[str, Any] | None:
        if self._resource_id is not None and self._lifecycle_manager is not None:
            resource_id = self._resource_id
            self._resource_id = None
            await self._lifecycle_manager.release_resource(
                resource_id,
                trial_id=self.trial_id,
                outcome_status=outcome_status,
                reason="container_finalize",
            )
            return None
        if self._session is None or self._provider is None:
            return None
        return await self._close_registered_session()

    def prepare(self) -> ContainerSession | None:
        return _run_sync(self.prepare_phase()).session

    def close(self) -> dict[str, Any] | None:
        return _run_sync(self.finalize_phase())


def _run_sync(coro):  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Synchronous container runtime API cannot be used inside a running event loop; use prepare_phase/finalize_phase.")


__all__ = ["ContainerRuntime", "ContainerSession", "ContainerPrepareResult"]
