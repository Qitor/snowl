"""Benchmark adapter registry and built-in adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo
from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.errors import SnowlValidationError


AdapterFactory = Callable[..., BenchmarkAdapter]


@dataclass(frozen=True)
class RegisteredBenchmark:
    info: BenchmarkInfo
    factory: AdapterFactory


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegisteredBenchmark] = {}

    def register(self, name: str, info: BenchmarkInfo, factory: AdapterFactory) -> None:
        key = name.strip()
        if not key:
            raise SnowlValidationError("Benchmark name must be non-empty.")
        self._entries[key] = RegisteredBenchmark(info=info, factory=factory)

    def list(self) -> list[RegisteredBenchmark]:
        return [self._entries[k] for k in sorted(self._entries.keys())]

    def create(self, name: str, **kwargs: Any) -> BenchmarkAdapter:
        entry = self._entries.get(name)
        if entry is None:
            raise SnowlValidationError(f"Unknown benchmark adapter '{name}'.")
        return entry.factory(**kwargs)


_DEFAULT_BENCHMARK_REGISTRY = BenchmarkRegistry()


def get_default_benchmark_registry() -> BenchmarkRegistry:
    return _DEFAULT_BENCHMARK_REGISTRY


def register_builtin_benchmarks(registry: BenchmarkRegistry | None = None) -> BenchmarkRegistry:
    registry = registry or get_default_benchmark_registry()
    registry.register(
        name="agentsafetybench",
        info=BenchmarkInfo(name="agentsafetybench", description="Agent-SafetyBench benchmark adapter."),
        factory=lambda **kwargs: AgentSafetyBenchBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="jsonl",
        info=BenchmarkInfo(name="jsonl", description="Generic JSONL benchmark adapter."),
        factory=lambda **kwargs: JsonlBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="csv",
        info=BenchmarkInfo(name="csv", description="Generic CSV benchmark adapter."),
        factory=lambda **kwargs: CsvBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="strongreject",
        info=BenchmarkInfo(name="strongreject", description="StrongReject benchmark adapter."),
        factory=lambda **kwargs: StrongRejectBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="terminalbench",
        info=BenchmarkInfo(name="terminalbench", description="Terminal-Bench benchmark adapter."),
        factory=lambda **kwargs: TerminalBenchBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="osworld",
        info=BenchmarkInfo(name="osworld", description="OSWorld benchmark adapter."),
        factory=lambda **kwargs: OSWorldBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="toolemu",
        info=BenchmarkInfo(name="toolemu", description="ToolEmu benchmark adapter."),
        factory=lambda **kwargs: ToolEmuBenchmarkAdapter(**kwargs),
    )
    return registry


register_builtin_benchmarks()
