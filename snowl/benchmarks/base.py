"""Core benchmark adapter contracts and metadata schemas.

Framework role:
- Defines the interface concrete adapters must implement to integrate with Snowl benchmark execution.
- Defines `BenchmarkConcurrencyProfile` for benchmark-specific runtime budget guidance.

Runtime/usage wiring:
- Used by adapter implementations, registry, and conformance checks.
- Key top-level symbols in this file: `BenchmarkInfo`, `BenchmarkConcurrencyProfile`, `BenchmarkAdapter`, `validate_benchmark_adapter`.

Change guardrails:
- Any API change here is cross-adapter and high-impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from snowl.core import Task
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class BenchmarkConcurrencyProfile:
    """Benchmark-specific guidance for RuntimePolicy budget resolution.

    Attributes:
        name: Benchmark name (for logging and identification).
        api_call_amplification: Estimated LM API calls per trial. ToolEmu with emulation
            makes ~30 calls/trial; a simple QA makes ~1. Used to inform provider budget.
        recommended_max_running: Suggested max_running_trials for this benchmark.
            Applied when no explicit CLI/config override is provided.
        scorer_uses_provider: Whether the scorer makes model API calls that need
            provider admission (e.g., LLM-as-judge).
        scorer_provider_id: Provider ID for scorer model calls. Required when
            scorer_uses_provider is True.
        recommended_scoring_tasks: Suggested max_scoring_tasks. Applied when no
            explicit override is provided.
    """

    name: str
    api_call_amplification: float = 1.0
    recommended_max_running: int | None = None
    scorer_uses_provider: bool = False
    scorer_provider_id: str | None = None
    recommended_scoring_tasks: int | None = None


@dataclass(frozen=True)
class RiskDomain:
    """Risk domain descriptor for benchmark classification.

    Used by snowl-evals to tag benchmarks with the type of risk they evaluate.

    Attributes:
        domain_id: Machine-readable identifier (e.g. "unsafe_compliance").
        display_name: Human-readable name (e.g. "Unsafe Compliance").
        description: One-line explanation of the risk domain.
    """

    domain_id: str
    display_name: str = ""
    description: str = ""


@dataclass(frozen=True)
class BenchmarkInfo:
    name: str
    description: str
    display_name: str = ""
    short_description: str = ""
    domain: str = "uncategorized"
    benchmark_type: str = "capability"
    family: str = ""
    primary_metric: str = ""
    higher_is_better: bool = True
    sample_preview_mode: str = "qa"
    dashboard_tags: list[str] = field(default_factory=list)
    concurrency_profile: BenchmarkConcurrencyProfile | None = None
    middleware_hints: dict[str, Any] = field(default_factory=dict)
    risk_domains: tuple[RiskDomain, ...] = ()

    def __post_init__(self) -> None:
        if not self.display_name:
            object.__setattr__(self, "display_name", self.name)
        if not self.family:
            object.__setattr__(self, "family", self.name)


class BenchmarkAdapter(Protocol):
    info: BenchmarkInfo

    def list_splits(self) -> list[str]: ...

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]: ...


def validate_benchmark_adapter(adapter: BenchmarkAdapter) -> None:
    info = getattr(adapter, "info", None)
    if not isinstance(info, BenchmarkInfo):
        raise SnowlValidationError("BenchmarkAdapter.info must be a BenchmarkInfo instance.")

    if not callable(getattr(adapter, "list_splits", None)):
        raise SnowlValidationError("BenchmarkAdapter must implement list_splits().")

    if not callable(getattr(adapter, "load_tasks", None)):
        raise SnowlValidationError("BenchmarkAdapter must implement load_tasks(...).")

    _VALID_BENCHMARK_TYPES = {"capability", "safety"}
    _VALID_PREVIEW_MODES = {"qa", "dialog", "tool_trace", "gui_trace", "code_trace"}

    if info.benchmark_type not in _VALID_BENCHMARK_TYPES:
        raise SnowlValidationError(
            f"BenchmarkInfo.benchmark_type must be one of {_VALID_BENCHMARK_TYPES}, got '{info.benchmark_type}'."
        )
    if info.sample_preview_mode not in _VALID_PREVIEW_MODES:
        raise SnowlValidationError(
            f"BenchmarkInfo.sample_preview_mode must be one of {_VALID_PREVIEW_MODES}, got '{info.sample_preview_mode}'."
        )
