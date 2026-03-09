"""Common container runtime orchestration for benchmark agents."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from snowl.runtime.container_providers import (
    ContainerProvider,
    ContainerProviderContext,
    ContainerProviderRegistry,
    ContainerSession,
    default_container_provider_registry,
)


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

    def prepare(self) -> ContainerSession | None:
        benchmark = str(self.task_metadata.get("benchmark") or "").strip().lower()
        provider = self._provider_registry.resolve(benchmark)
        if provider is None:
            return None
        context = self._context()
        self._provider = provider
        self._session = provider.prepare(context)
        return self._session

    def close(self) -> dict[str, Any] | None:
        if self._session is None or self._provider is None:
            return None
        session = self._session
        provider = self._provider
        self._session = None
        self._provider = None
        return provider.close(self._context(), session)


__all__ = ["ContainerRuntime", "ContainerSession"]
