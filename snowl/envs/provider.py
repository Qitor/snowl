"""Environment provider abstraction for pluggable sandbox backends.

Framework role:
- Defines EnvironmentProvider ABC and EnvironmentHandle for sandbox lifecycle.
- Provides EnvironmentProviderRegistry for name-based lookup with entry_points.
- DockerProvider and LocalProvider are built-in implementations.

Runtime/usage wiring:
- Used by the runtime when selecting a sandbox backend based on project.yml config.
- DockerProvider wraps existing ContainerBackend; LocalProvider wraps CommandRunner.
- Future cloud providers (E2B, Modal, Daytona) will implement this ABC.

Change guardrails:
- Provider implementations may import third-party SDKs (docker, cloud SDKs).
- Provider ABC should stay lightweight; no heavy dependencies in this module.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from snowl.core.env import SandboxSpec


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnvironmentCapabilities:
    """Declared capabilities of an environment provider."""

    supported_ops: tuple[str, ...] = ()
    supports_networking: bool = False
    supports_gui: bool = False
    max_duration_seconds: float | None = None
    max_concurrent: int | None = None


@dataclass
class EnvironmentHandle:
    """Opaque handle returned by provider.prepare()."""

    environment_id: str
    provider_name: str
    capabilities: EnvironmentCapabilities = field(default_factory=EnvironmentCapabilities)
    metadata: dict[str, Any] = field(default_factory=dict)
    _backend_ref: Any = None  # Provider-specific backend reference


# ---------------------------------------------------------------------------
# EnvironmentProvider ABC
# ---------------------------------------------------------------------------

class EnvironmentProvider(ABC):
    """Abstract base class for environment providers.

    Lifecycle::

        handle = await provider.prepare(spec)
        result = await provider.execute(handle, command)
        await provider.teardown(handle)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'docker', 'local', 'e2b', 'modal')."""
        ...

    @abstractmethod
    async def prepare(self, spec: SandboxSpec) -> EnvironmentHandle:
        """Prepare an environment matching the given spec."""
        ...

    @abstractmethod
    async def execute(
        self,
        handle: EnvironmentHandle,
        command: str,
        *,
        timeout_seconds: float | None = None,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command in the environment.

        Returns:
            Dict with at least 'exit_code', 'stdout', 'stderr'.
        """
        ...

    @abstractmethod
    async def teardown(self, handle: EnvironmentHandle) -> dict[str, Any]:
        """Tear down the environment and release resources."""
        ...

    def describe_capabilities(self) -> EnvironmentCapabilities:
        """Describe this provider's capabilities."""
        return EnvironmentCapabilities()


# ---------------------------------------------------------------------------
# DockerProvider
# ---------------------------------------------------------------------------

class DockerProvider(EnvironmentProvider):
    """Environment provider backed by Docker containers.

    Wraps the existing ContainerBackend for container lifecycle management.
    """

    @property
    def name(self) -> str:
        return "docker"

    async def prepare(self, spec: SandboxSpec) -> EnvironmentHandle:
        from snowl.envs.substrate.command_runner import CommandRunner
        from snowl.envs.substrate.container_backend import ContainerBackend

        runner = CommandRunner()
        backend = ContainerBackend(command_runner=runner)

        image = spec.image
        if not image:
            raise ValueError("DockerProvider requires SandboxSpec.image")

        result = await asyncio.to_thread(
            backend.run,
            image=image,
            command="sleep infinity",
            detach=True,
            env=spec.environment or None,
            network=spec.network.get("mode") if spec.network else None,
        )
        container_id = str(result.get("stdout", "")).strip().split("\n")[-1]
        if not container_id:
            container_id = str(result.get("container_id", ""))

        return EnvironmentHandle(
            environment_id=container_id,
            provider_name=self.name,
            capabilities=EnvironmentCapabilities(
                supported_ops=("process.run", "file.read", "file.write"),
                supports_networking=bool(spec.network),
            ),
            metadata={"image": image, "spec_hash": spec.spec_hash()},
            _backend_ref=backend,
        )

    async def execute(
        self,
        handle: EnvironmentHandle,
        command: str,
        *,
        timeout_seconds: float | None = None,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        backend = handle._backend_ref
        return await asyncio.to_thread(
            backend.exec,
            container_id=handle.environment_id,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
        )

    async def teardown(self, handle: EnvironmentHandle) -> dict[str, Any]:
        backend = handle._backend_ref
        return await asyncio.to_thread(
            backend.rm,
            container_id=handle.environment_id,
            force=True,
        )

    def describe_capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(
            supported_ops=("process.run", "file.read", "file.write"),
            supports_networking=True,
        )


# ---------------------------------------------------------------------------
# LocalProvider
# ---------------------------------------------------------------------------

class LocalProvider(EnvironmentProvider):
    """Environment provider for local (no-container) execution."""

    @property
    def name(self) -> str:
        return "local"

    async def prepare(self, spec: SandboxSpec) -> EnvironmentHandle:
        return EnvironmentHandle(
            environment_id=f"local-{spec.spec_hash()[:12]}",
            provider_name=self.name,
            capabilities=EnvironmentCapabilities(
                supported_ops=("process.run", "file.read", "file.write"),
                supports_networking=True,
            ),
            metadata={"spec_hash": spec.spec_hash()},
        )

    async def execute(
        self,
        handle: EnvironmentHandle,
        command: str,
        *,
        timeout_seconds: float | None = None,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        from snowl.envs.substrate.command_runner import CommandRunner

        runner = CommandRunner(cwd=workdir)
        return await asyncio.to_thread(
            runner.run,
            ["bash", "-lc", command],
            timeout_seconds=timeout_seconds,
        )

    async def teardown(self, handle: EnvironmentHandle) -> dict[str, Any]:
        return {"environment_id": handle.environment_id, "provider": self.name}

    def describe_capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(
            supported_ops=("process.run", "file.read", "file.write"),
            supports_networking=True,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class EnvironmentProviderRegistry:
    """Registry of environment providers, keyed by provider name."""

    def __init__(self) -> None:
        self._providers: dict[str, type[EnvironmentProvider]] = {}

    def register(self, name: str, provider_cls: type[EnvironmentProvider]) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Provider name must be a non-empty string.")
        if not (isinstance(provider_cls, type) and issubclass(provider_cls, EnvironmentProvider)):
            raise TypeError(
                f"Must be an EnvironmentProvider subclass, got {provider_cls!r}"
            )
        self._providers[name.strip()] = provider_cls

    def get(self, name: str) -> EnvironmentProvider:
        if name not in self._providers:
            available = ", ".join(sorted(self._providers)) or "(none)"
            raise KeyError(
                f"No environment provider '{name}'. Available: {available}"
            )
        return self._providers[name]()

    def has(self, name: str) -> bool:
        return name in self._providers

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    @classmethod
    def from_entry_points(
        cls, group: str = "snowl.envs.providers"
    ) -> "EnvironmentProviderRegistry":
        """Create a registry populated from Python entry_points."""
        registry = cls()
        if sys.version_info >= (3, 12):
            eps = importlib.metadata.entry_points(group=group)
        else:
            all_eps = importlib.metadata.entry_points()
            eps = all_eps.get(group, []) if isinstance(all_eps, dict) else [
                ep for ep in all_eps
                if getattr(ep, "group", None) == group
            ]
        for ep in eps:
            try:
                provider_cls = ep.load()
                if isinstance(provider_cls, type) and issubclass(
                    provider_cls, EnvironmentProvider
                ):
                    registry.register(ep.name, provider_cls)
            except Exception:
                pass
        return registry


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

_default_registry: EnvironmentProviderRegistry | None = None


def default_environment_provider_registry() -> EnvironmentProviderRegistry:
    """Return the default registry with built-in providers + entry_points."""
    global _default_registry
    if _default_registry is None:
        registry = EnvironmentProviderRegistry()
        registry.register("docker", DockerProvider)
        registry.register("local", LocalProvider)
        # Discover from entry_points
        try:
            ep_registry = EnvironmentProviderRegistry.from_entry_points()
            for name in ep_registry.list_providers():
                if not registry.has(name):
                    registry._providers[name] = ep_registry._providers[name]
        except Exception:
            pass
        _default_registry = registry
    return _default_registry
