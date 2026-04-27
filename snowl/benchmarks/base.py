"""Core benchmark adapter contracts and metadata schemas.

Framework role:
- Defines the interface concrete adapters must implement to integrate with Snowl benchmark execution.

Runtime/usage wiring:
- Used by adapter implementations, registry, and conformance checks.
- Key top-level symbols in this file: `BenchmarkInfo`, `BenchmarkAdapter`, `validate_benchmark_adapter`.

Change guardrails:
- Any API change here is cross-adapter and high-impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from snowl.core import Task
from snowl.errors import SnowlValidationError


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
