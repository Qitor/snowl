"""Reusable row-oriented adapter template for benchmark implementations.

Framework role:
- Encapsulates common split/filter/sample-to-task plumbing so benchmark adapters only implement domain-specific mapping hooks.

Runtime/usage wiring:
- Subclassed by concrete adapters in benchmark packages.
- Key top-level symbols in this file: `BaseBenchmarkAdapter`.

Change guardrails:
- Template behavior changes fan out to many adapters; validate broadly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, TypeVar

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.utils import build_benchmark_task, matches_filters, normalize_split
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError

RowT = TypeVar("RowT")


class BaseBenchmarkAdapter(ABC, Generic[RowT]):
    """Template-method base class for adapters that iterate over dataset rows."""

    name: str
    description: str
    default_split: str = "test"
    stringify_filter_values: bool = True

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def list_splits(self) -> list[str]:
        splits: set[str] = set()
        for row_index, row in enumerate(self._iter_rows(), start=1):
            splits.add(self._normalize_split(self._row_split(row, row_index=row_index)))
        return sorted(splits) if splits else [self.default_split]

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]:
        requested_split = self._normalize_split(split)
        self._validate_split_request(requested_split)
        filters = filters or {}

        selected: list[dict[str, Any]] = []
        for row_index, row in enumerate(self._iter_rows(), start=1):
            row_split = self._normalize_split(self._row_split(row, row_index=row_index))
            if row_split != requested_split:
                continue
            if not self._matches_filters(row, filters):
                continue
            sample = self._row_to_sample(
                row,
                row_index=row_index,
                row_split=row_split,
                selected_count=len(selected),
            )
            if sample is None:
                continue
            selected.append(sample)
            if limit is not None and len(selected) >= limit:
                break

        if not selected:
            raise SnowlValidationError(self._no_samples_error(requested_split))

        task = build_benchmark_task(
            benchmark=self.name,
            split=requested_split,
            samples=selected,
            env_spec=self._env_spec(),
            metadata=self._task_metadata(split=requested_split, selected_count=len(selected)),
        )
        return [task]

    @abstractmethod
    def _iter_rows(self) -> list[RowT]:
        """Return benchmark rows in deterministic order."""

    @abstractmethod
    def _row_split(self, row: RowT, *, row_index: int) -> str:
        """Return split string for a row."""

    @abstractmethod
    def _row_to_sample(
        self,
        row: RowT,
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        """Transform a row into a benchmark sample."""

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _validate_split_request(self, split: str) -> None:
        _ = split

    def _normalize_split(self, split: object) -> str:
        return normalize_split(split, self.default_split)

    def _row_filter_value(self, row: RowT, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    def _filter_comparators(self) -> dict[str, Any]:
        return {}

    def _matches_filters(self, row: RowT, filters: dict[str, Any]) -> bool:
        return matches_filters(
            filters=filters,
            resolver=lambda key: self._row_filter_value(row, key),
            stringify=self.stringify_filter_values,
            comparators=self._filter_comparators(),
        )

    def _dataset_path_str(self) -> str | None:
        dataset_path = getattr(self, "dataset_path", None)
        if dataset_path is None:
            return None
        return str(Path(str(dataset_path)))

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "benchmark": self.name,
            "split": split,
            "sample_count": selected_count,
        }
        dataset_path = self._dataset_path_str()
        if dataset_path:
            metadata["dataset_path"] = dataset_path
        return metadata

    def _no_samples_error(self, split: str) -> str:
        dataset_path = self._dataset_path_str() or "<dataset>"
        return f"No {self.name} samples loaded for split='{split}' in {dataset_path}."
