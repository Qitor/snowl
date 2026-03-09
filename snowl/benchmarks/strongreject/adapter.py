"""StrongReject benchmark adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path, read_csv_rows
from snowl.core import EnvSpec


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "strongreject",
        "strongreject_dataset",
        "strongreject_small_dataset.csv",
    )


@dataclass(frozen=True)
class StrongRejectBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "strongreject"
    description: str = "StrongReject benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    prompt_field: str = "forbidden_prompt"
    id_field: str = "id"

    def _iter_rows(self) -> list[dict[str, Any]]:
        return read_csv_rows(
            self.dataset_path,
            not_found_message="StrongReject dataset file not found",
        )

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get(self.split_field) or self.default_split)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        prompt = str(row.get(self.prompt_field) or "").strip()
        if not prompt:
            return None

        sample_id = str(row.get(self.id_field) or "").strip()
        if not sample_id:
            digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
            sample_id = f"sr-{row_index:06d}-{digest}"

        return {
            "id": sample_id,
            "input": prompt,
            "metadata": {
                "target": "",
                "forbidden_prompt": prompt,
                "category": row.get("category"),
                "source": row.get("source"),
                "split": row_split,
                "raw_row": dict(row),
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        _ = selected_count
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(self.dataset_path),
            "scoring": "strongreject",
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No StrongReject samples loaded for split='{split}' in {self.dataset_path}."
