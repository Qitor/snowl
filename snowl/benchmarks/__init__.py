"""Benchmark package facade exposing adapters, registry, and conformance utilities.

Framework role:
- Provides one import surface for built-in benchmark adapters plus registry APIs used by CLI/eval bootstrap.

Runtime/usage wiring:
- Used by benchmark command paths and tests to construct adapters without hardcoding module paths.

Change guardrails:
- Keep re-exports aligned with registry defaults and benchmark docs.
"""

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo, RiskDomain, validate_benchmark_adapter
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.manifest import BenchmarkManifest, load_manifest
from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.conformance import ConformanceReport, run_conformance
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.benchmarks.registry import (
    BenchmarkRegistry,
    RegisteredBenchmark,
    _lazy_factory,
    get_default_benchmark_registry,
    register_builtin_benchmarks,
)

__all__ = [
    "BenchmarkAdapter",
    "BenchmarkInfo",
    "BaseBenchmarkAdapter",
    "BenchmarkManifest",
    "BenchmarkRegistry",
    "RiskDomain",
    "AgentSafetyBenchBenchmarkAdapter",
    "ConformanceReport",
    "CsvBenchmarkAdapter",
    "JsonlBenchmarkAdapter",
    "OSWorldBenchmarkAdapter",
    "RegisteredBenchmark",
    "StrongRejectBenchmarkAdapter",
    "TerminalBenchBenchmarkAdapter",
    "ToolEmuBenchmarkAdapter",
    "_lazy_factory",
    "get_default_benchmark_registry",
    "load_manifest",
    "register_builtin_benchmarks",
    "run_conformance",
    "validate_benchmark_adapter",
]
