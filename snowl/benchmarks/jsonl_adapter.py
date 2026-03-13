"""Generic JSONL-to-Task adapter used for schema-light benchmark integration.

Framework role:
- Implements `BaseBenchmarkAdapter` hooks for split filtering and conversion of JSONL rows into Snowl samples.
- Preserves extra row fields in `metadata` so benchmark-specific signals remain available to scorers.

Runtime/usage wiring:
- Used in benchmark flows that want immediate JSONL support without custom adapter code.

Change guardrails:
- Treat default field names and sample-id fallback behavior as user-facing compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_jsonl_rows
from snowl.core import EnvSpec


@dataclass(frozen=True)
class JsonlBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Loads a JSONL benchmark file into a Task with homogeneous schema."""

    dataset_path: str
    name: str = "jsonl"
    description: str = "Generic JSONL benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    input_field: str = "input"
    target_field: str = "target"
    id_field: str = "id"
    stringify_filter_values: bool = False

    def _iter_rows(self) -> list[dict[str, Any]]:
        return read_jsonl_rows(
            self.dataset_path,
            not_found_message="JSONL benchmark file not found",
        )

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get(self.split_field, self.default_split))

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any]:
        _ = row_index
        return {
            "id": row.get(self.id_field) or f"{row_split}-{selected_count + 1}",
            "input": row.get(self.input_field, ""),
            "target": row.get(self.target_field),
            "metadata": {k: v for k, v in row.items() if k not in {self.input_field, self.target_field}},
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        _ = selected_count
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(self.dataset_path),
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No benchmark samples loaded for split='{split}' in {self.dataset_path}."
