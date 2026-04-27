"""Benchmark adapter registry and built-in adapter wiring table.

Framework role:
- Maps benchmark names to factories and exposes creation/listing APIs used by CLI and benchmark orchestration.
- Central place for adding/removing built-in benchmark integrations.

Runtime/usage wiring:
- Imported by benchmark command flow to resolve adapters by name.
- Key top-level symbols in this file: `RegisteredBenchmark`, `BenchmarkRegistry`, `get_default_benchmark_registry`, `register_builtin_benchmarks`.

Change guardrails:
- Registration keys are user-facing CLI contract; treat renames/removals as breaking changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo
from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.benchmarks.mask import MASKBenchmarkAdapter
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.benchmarks.wmdp import WMDPBenchmarkAdapter
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
        info=BenchmarkInfo(
            name="agentsafetybench",
            description="Agent-SafetyBench benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentsafetybench",
            primary_metric="safety_rate",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["agent_safety"],
        ),
        factory=lambda **kwargs: AgentSafetyBenchBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="jsonl",
        info=BenchmarkInfo(
            name="jsonl",
            description="Generic JSONL benchmark adapter.",
        ),
        factory=lambda **kwargs: JsonlBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="csv",
        info=BenchmarkInfo(
            name="csv",
            description="Generic CSV benchmark adapter.",
        ),
        factory=lambda **kwargs: CsvBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="strongreject",
        info=BenchmarkInfo(
            name="strongreject",
            description="StrongReject benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="strongreject",
            primary_metric="strongreject",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["jailbreak", "refusal"],
        ),
        factory=lambda **kwargs: StrongRejectBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="terminalbench",
        info=BenchmarkInfo(
            name="terminalbench",
            description="Terminal-Bench benchmark adapter.",
            domain="cyber_offense",
            benchmark_type="capability",
            family="terminalbench",
            primary_metric="pass_rate",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["coding", "terminal"],
        ),
        factory=lambda **kwargs: TerminalBenchBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="osworld",
        info=BenchmarkInfo(
            name="osworld",
            description="OSWorld benchmark adapter.",
            domain="cyber_offense",
            benchmark_type="capability",
            family="osworld",
            primary_metric="success_rate",
            higher_is_better=True,
            sample_preview_mode="gui_trace",
            dashboard_tags=["gui", "desktop", "agent_capability"],
        ),
        factory=lambda **kwargs: OSWorldBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="toolemu",
        info=BenchmarkInfo(
            name="toolemu",
            description="ToolEmu benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="toolemu",
            primary_metric="risk_rate",
            higher_is_better=False,
            sample_preview_mode="tool_trace",
            dashboard_tags=["tool_use", "agent_risk"],
        ),
        factory=lambda **kwargs: ToolEmuBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="wmdp-cyber",
        info=BenchmarkInfo(
            name="wmdp-cyber",
            description="WMDP-Cyber benchmark adapter.",
            display_name="WMDP Cyber",
            short_description="WMDP cyber multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="wmdp",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
        ),
        factory=lambda **kwargs: WMDPBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="wmdp-chem",
        info=BenchmarkInfo(
            name="wmdp-chem",
            description="WMDP-Chem benchmark adapter.",
            display_name="WMDP Chem",
            short_description="WMDP chemistry multiple-choice benchmark",
            domain="chemical_risks",
            benchmark_type="capability",
            family="wmdp",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "chemistry"],
        ),
        factory=lambda **kwargs: WMDPBenchmarkAdapter(variant="wmdp-chem", **kwargs),
    )
    registry.register(
        name="mask",
        info=BenchmarkInfo(
            name="mask",
            description="MASK benchmark adapter.",
            display_name="MASK",
            short_description="Model Alignment between Sycophancy and Knowledge",
            domain="agentic_safety",
            benchmark_type="safety",
            family="mask",
            primary_metric="mask_score",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["situational_awareness", "deception"],
        ),
        factory=lambda **kwargs: MASKBenchmarkAdapter(**kwargs),
    )
    return registry


register_builtin_benchmarks()
