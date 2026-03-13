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
        provider_registry: ContainerProviderRegistry | None = None,
    ) -> None:
        self.task_id = task_id
        self.agent_id = agent_id
        self.variant_id = variant_id
        self.task_env_type = task_env_type
        self.task_metadata = dict(task_metadata or {})
        self.sample = dict(sample or {})
        self._emit = emit if callable(emit) else None
        self._provider_registry = provider_registry or default_container_provider_registry()
        self._provider: ContainerProvider | None = None
        self._session: ContainerSession | None = None

    def _context(self) -> ContainerProviderContext:
        return ContainerProviderContext(
            task_id=self.task_id,
            agent_id=self.agent_id,
            variant_id=self.variant_id,
            task_env_type=self.task_env_type,
            task_metadata=self.task_metadata,
            sample=self.sample,
            emit=self._emit,
        )

    def _resolve_provider(self) -> tuple[str, ContainerProvider | None]:
        benchmark = str(self.task_metadata.get("benchmark") or "").strip().lower()
        provider = self._provider_registry.resolve(benchmark)
        return benchmark, provider

    def describe_requirements(self) -> dict[str, Any]:
        benchmark, provider = self._resolve_provider()
        if provider is None:
            return {
                "benchmark": benchmark,
                "requires_container": False,
                "requires_build": False,
                "spec_hash": None,
                "prepare_provider_ids": (),
            }
        return dict(provider.describe_requirements(self._context()))

    async def prepare_phase(self) -> ContainerPrepareResult:
        benchmark, provider = self._resolve_provider()
        if provider is None:
            return ContainerPrepareResult(
                session=None,
                requires_container=False,
                requires_build=False,
                spec_hash=None,
                prepare_provider_ids=(),
                metadata={"benchmark": benchmark},
            )
        context = self._context()
        self._provider = provider
        requirements = dict(provider.describe_requirements(context))
        self._session = await provider.prepare(context)
        return ContainerPrepareResult(
            session=self._session,
            requires_container=bool(requirements.get("requires_container", True)),
            requires_build=bool(requirements.get("requires_build", False)),
            spec_hash=(str(requirements.get("spec_hash")) if requirements.get("spec_hash") else None),
            prepare_provider_ids=tuple(str(x) for x in (requirements.get("prepare_provider_ids") or ()) if str(x).strip()),
            metadata=requirements,
        )

    async def finalize_phase(self) -> dict[str, Any] | None:
        if self._session is None or self._provider is None:
            return None
        session = self._session
        provider = self._provider
        self._session = None
        self._provider = None
        return await provider.close(self._context(), session)

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
