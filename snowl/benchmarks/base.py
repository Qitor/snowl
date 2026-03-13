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

from dataclasses import dataclass
from typing import Any, Protocol

from snowl.core import Task
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class BenchmarkInfo:
    name: str
    description: str


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
