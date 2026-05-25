"""Unified registry facade for all Snowl components.

Framework role:
- Provides a single entry point wrapping BenchmarkRegistry, AdapterRegistry,
  and EnvironmentProviderRegistry.
- ``doctor()`` diagnostic checks all sub-registries for health.
- ``list_all()`` / ``info()`` give unified component discovery.

Runtime/usage wiring:
- CLI commands and user code import ``get_registry()`` for component lookup.
- Each sub-registry remains independently usable; the facade delegates.

Change guardrails:
- This is a facade only — no new registration logic lives here.
- Sub-registry APIs are the source of truth; facade methods are thin wrappers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from snowl.adapters.registry import AdapterRegistry, get_default_adapter_registry
from snowl.benchmarks.registry import BenchmarkRegistry, get_default_benchmark_registry
from snowl.envs.provider import (
    EnvironmentProviderRegistry,
    default_environment_provider_registry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistryEntry:
    """A unified entry from any sub-registry."""

    name: str
    kind: str  # "benchmark" | "adapter" | "environment_provider"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorResult:
    """Result of running registry health diagnostics."""

    ok: bool
    checks: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SnowlRegistry facade
# ---------------------------------------------------------------------------

class SnowlRegistry:
    """Unified facade over all Snowl sub-registries.

    Wraps BenchmarkRegistry, AdapterRegistry, and
    EnvironmentProviderRegistry with a single interface for listing,
    lookup, and diagnostics.
    """

    def __init__(
        self,
        benchmarks: BenchmarkRegistry | None = None,
        adapters: AdapterRegistry | None = None,
        env_providers: EnvironmentProviderRegistry | None = None,
    ) -> None:
        self.benchmarks = benchmarks or get_default_benchmark_registry()
        self.adapters = adapters or get_default_adapter_registry()
        self.env_providers = env_providers or default_environment_provider_registry()

    # -- listing -------------------------------------------------------------

    def list_all(self) -> list[RegistryEntry]:
        """List entries from all sub-registries."""
        return (
            self.list_benchmarks()
            + self.list_adapters()
            + self.list_env_providers()
        )

    def list_benchmarks(self) -> list[RegistryEntry]:
        """List benchmark entries."""
        entries: list[RegistryEntry] = []
        for rb in self.benchmarks.list():
            entries.append(RegistryEntry(
                name=rb.info.name,
                kind="benchmark",
                description=rb.info.description,
                metadata={"family": rb.info.family, "domain": rb.info.domain},
            ))
        return entries

    def list_adapters(self) -> list[RegistryEntry]:
        """List framework adapter entries."""
        entries: list[RegistryEntry] = []
        for name in self.adapters.list_frameworks():
            entries.append(RegistryEntry(
                name=name,
                kind="adapter",
            ))
        return entries

    def list_env_providers(self) -> list[RegistryEntry]:
        """List environment provider entries."""
        entries: list[RegistryEntry] = []
        for name in self.env_providers.list_providers():
            entries.append(RegistryEntry(
                name=name,
                kind="environment_provider",
            ))
        return entries

    # -- lookup --------------------------------------------------------------

    def info(self, name: str) -> RegistryEntry:
        """Look up a named entry across all sub-registries.

        Raises:
            KeyError: If no entry is found with the given name.
        """
        # Check benchmarks
        for rb in self.benchmarks.list():
            if rb.info.name == name:
                return RegistryEntry(
                    name=rb.info.name,
                    kind="benchmark",
                    description=rb.info.description,
                    metadata={"family": rb.info.family, "domain": rb.info.domain},
                )

        # Check adapters
        if self.adapters.has(name):
            return RegistryEntry(name=name, kind="adapter")

        # Check env providers
        if self.env_providers.has(name):
            return RegistryEntry(name=name, kind="environment_provider")

        raise KeyError(f"No registry entry found for '{name}'")

    # -- diagnostics ---------------------------------------------------------

    def doctor(self) -> DoctorResult:
        """Run diagnostic checks on all sub-registries.

        Checks:
        - Each sub-registry is non-empty.
        - Each registered benchmark factory can be called without error.
        - Each registered adapter can be instantiated.
        - Each registered environment provider can be instantiated.
        - Cross-registry name uniqueness (warning, not error).
        """
        checks: list[dict[str, Any]] = []
        all_ok = True

        # Benchmark registry non-empty
        benchmark_list = self.benchmarks.list()
        checks.append({
            "check": "benchmarks_non_empty",
            "ok": len(benchmark_list) > 0,
            "detail": f"{len(benchmark_list)} benchmarks registered",
        })
        if not benchmark_list:
            all_ok = False

        # Benchmark factory health (sample first 5 to keep fast)
        for rb in benchmark_list[:5]:
            try:
                self.benchmarks.create(rb.info.name)
                checks.append({
                    "check": "benchmark_factory",
                    "ok": True,
                    "detail": f"benchmark '{rb.info.name}' factory works",
                })
            except Exception as exc:
                all_ok = False
                checks.append({
                    "check": "benchmark_factory",
                    "ok": False,
                    "detail": f"benchmark '{rb.info.name}' factory failed: {exc}",
                })

        # Adapter registry non-empty
        adapter_names = self.adapters.list_frameworks()
        checks.append({
            "check": "adapters_non_empty",
            "ok": len(adapter_names) > 0,
            "detail": f"{len(adapter_names)} adapters registered",
        })
        if not adapter_names:
            all_ok = False

        # Adapter instantiation
        for name in adapter_names[:5]:
            try:
                self.adapters.get(name)
                checks.append({
                    "check": "adapter_factory",
                    "ok": True,
                    "detail": f"adapter '{name}' instantiates",
                })
            except Exception as exc:
                all_ok = False
                checks.append({
                    "check": "adapter_factory",
                    "ok": False,
                    "detail": f"adapter '{name}' failed: {exc}",
                })

        # Env provider registry non-empty
        provider_names = self.env_providers.list_providers()
        checks.append({
            "check": "env_providers_non_empty",
            "ok": len(provider_names) > 0,
            "detail": f"{len(provider_names)} env providers registered",
        })
        if not provider_names:
            all_ok = False

        # Env provider instantiation
        for name in provider_names[:5]:
            try:
                self.env_providers.get(name)
                checks.append({
                    "check": "env_provider_factory",
                    "ok": True,
                    "detail": f"env_provider '{name}' instantiates",
                })
            except Exception as exc:
                all_ok = False
                checks.append({
                    "check": "env_provider_factory",
                    "ok": False,
                    "detail": f"env_provider '{name}' failed: {exc}",
                })

        # Cross-registry name uniqueness
        benchmark_names = {rb.info.name for rb in benchmark_list}
        adapter_name_set = set(adapter_names)
        provider_name_set = set(provider_names)
        dupes = (
            (benchmark_names & adapter_name_set)
            | (benchmark_names & provider_name_set)
            | (adapter_name_set & provider_name_set)
        )
        if dupes:
            checks.append({
                "check": "cross_registry_uniqueness",
                "ok": True,  # Warning, not error
                "detail": f"names appear in multiple registries: {sorted(dupes)}",
            })

        return DoctorResult(ok=all_ok, checks=checks)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_default_registry: SnowlRegistry | None = None


def get_registry() -> SnowlRegistry:
    """Return the global SnowlRegistry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SnowlRegistry()
    return _default_registry
