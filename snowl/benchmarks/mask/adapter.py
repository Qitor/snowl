"""MASK (Model Alignment between Sycophancy and Knowledge) benchmark adapter.

Maps MASK dialog-based datasets into Snowl task/sample contracts.
Measures whether models maintain truthful behavior under social pressure.

Framework role:
- Owns benchmark-specific row iteration, split logic, and dialog sample formatting.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry and executed through the shared eval pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path, read_jsonl_rows
from snowl.core import EnvSpec


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "mask",
        "mask",
        "mask_dataset.jsonl",
    )


@dataclass(frozen=True)
class MASKBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "mask"
    description: str = "MASK benchmark adapter."
    default_split: str = "test"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="MASK",
            short_description="Model Alignment between Sycophancy and Knowledge",
            domain="agentic_safety",
            benchmark_type="safety",
            family="mask",
            primary_metric="mask_score",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["situational_awareness", "deception"],
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        dialog = row.get("dialog", [])
        if isinstance(dialog, list) and dialog:
            preview = str(dialog[0])[:200]
        else:
            preview = row.get("question", "")[:200]
        return {
            "id": row.get("id", ""),
            "input_preview": preview,
            "category": row.get("category", ""),
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"scoring": "mask"}

    def _iter_rows(self) -> list[dict[str, Any]]:
        return read_jsonl_rows(
            self.dataset_path,
            not_found_message=f"MASK dataset file not found: {self.dataset_path}",
        )

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split", "test"))

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        question = str(row.get("question", "")).strip()
        if not question:
            return None

        sample_id = str(row.get("id", "")).strip()
        if not sample_id:
            digest = hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]
            sample_id = f"mask-{row_index:06d}-{digest}"

        return {
            "id": sample_id,
            "input": question,
            "metadata": {
                "category": row.get("category", ""),
                "dialog": row.get("dialog", []),
                "split": row_split,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _no_samples_error(self, split: str) -> str:
        return f"No MASK samples loaded for split='{split}' in {self.dataset_path}."
