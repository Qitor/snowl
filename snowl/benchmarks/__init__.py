"""Benchmark adapters and registry."""

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo, validate_benchmark_adapter
from snowl.benchmarks.conformance import ConformanceReport, run_conformance
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.registry import (
    BenchmarkRegistry,
    RegisteredBenchmark,
    get_default_benchmark_registry,
    register_builtin_benchmarks,
)

__all__ = [
    "BenchmarkAdapter",
    "BenchmarkInfo",
    "BenchmarkRegistry",
    "ConformanceReport",
    "CsvBenchmarkAdapter",
    "JsonlBenchmarkAdapter",
    "OSWorldBenchmarkAdapter",
    "RegisteredBenchmark",
    "StrongRejectBenchmarkAdapter",
    "TerminalBenchBenchmarkAdapter",
    "get_default_benchmark_registry",
    "register_builtin_benchmarks",
    "run_conformance",
    "validate_benchmark_adapter",
]
