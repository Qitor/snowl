"""XSTest benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import HFDatasetAsset, stable_benchmark_id


DATASET_PATH = "walledai/XSTest"
DATASET_REVISION = "f1d713187c61b6ae64e602d74f0b3d812cc2e8e8"


@dataclass(frozen=True)
class XSTestBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    subset: Literal["safe", "unsafe"] = "safe"
    rows: list[dict[str, Any]] | None = None
    name: str = "xstest"
    description: str = "XSTest benchmark adapter."
    default_split: str = "test"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="XSTest",
            short_description="Exaggerated safety behavior and unsafe prompt refusal benchmark",
            domain="agentic_safety",
            benchmark_type="safety",
            family="xstest",
            primary_metric="xstest_safety",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["refusal", "overrefusal"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        return HFDatasetAsset(
            source=DATASET_PATH,
            revision=DATASET_REVISION,
            split="test",
            cache_tag="xstest",
        ).load_rows()

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = (row, row_index)
        return "test"

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, row_split, selected_count)
        if str(row.get("label") or "").strip() != self.subset:
            return None
        prompt = str(row.get("prompt") or "").strip()
        if not prompt:
            return None
        return {
            "id": stable_benchmark_id("xstest", prompt),
            "input": prompt,
            "metadata": {
                "type": row.get("type"),
                "note": row.get("note"),
                "label": row.get("label"),
                "focus": row.get("focus"),
                "subset": self.subset,
            },
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        _ = task
        return {"scoring": "xstest_refusal", "subset": self.subset}

    def _no_samples_error(self, split: str) -> str:
        return f"No XSTest samples loaded for split='{split}', subset='{self.subset}'."
