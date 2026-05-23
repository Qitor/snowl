"""AgentHarm benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import HFSnapshotFileAsset


DATASET_PATH = "ai-safety-institute/AgentHarm"
DATASET_REVISION = "e23b3fe60a0da9037314b88e5ee3a0c054970dad"

_SPLIT_FILES = {
    "harmful": {
        "val": "benchmark/harmful_behaviors_validation.json",
        "test_public": "benchmark/harmful_behaviors_test_public.json",
        "test_private": "benchmark/harmful_behaviors_test_private.json",
    },
    "benign": {
        "val": "benchmark/benign_behaviors_validation.json",
        "test_public": "benchmark/benign_behaviors_test_public.json",
        "test_private": "benchmark/benign_behaviors_test_private.json",
    },
}


def _coerce_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return None


@dataclass(frozen=True)
class AgentHarmBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    mode: Literal["harmful", "benign"] = "harmful"
    behavior_ids: str | list[str] | None = None
    detailed_behaviors: bool | str | None = None
    hint_included: bool | str | None = None
    rows: list[dict[str, Any]] | None = None
    name: str = "agentharm"
    description: str = "AgentHarm benchmark adapter."
    default_split: str = "test_public"
    stringify_filter_values: bool = False

    def __post_init__(self) -> None:
        if self.mode == "benign" and self.name == "agentharm":
            object.__setattr__(self, "name", "agentharm_benign")

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="AgentHarm" if self.mode == "harmful" else "AgentHarm Benign",
            short_description="Harmfulness potential in AI agents",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentharm",
            primary_metric="agentharm_safety",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["agent_safety", "tool_use", "refusal"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        rows: list[dict[str, Any]] = []
        for split, relative in _SPLIT_FILES[self.mode].items():
            path = HFSnapshotFileAsset(
                source=DATASET_PATH,
                revision=DATASET_REVISION,
                relative_path=relative,
                allow_patterns=("benchmark/*.json",),
                cache_tag="agentharm",
            ).resolve_path()
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data.get("behaviors", []):
                if isinstance(record, dict):
                    rows.append({**record, "split": split})
        return rows

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or self.default_split)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, row_split, selected_count)
        if not self._passes_adapter_filters(row):
            return None
        prompt = str(row.get("prompt") or "").strip()
        if not prompt:
            return None
        target_functions = [str(x) for x in (row.get("target_functions") or []) if str(x).strip()]
        return {
            "id": str(row.get("id") or f"{self.name}-{selected_count + 1}"),
            "input": prompt,
            "metadata": {
                "id": row.get("id"),
                "id_original": row.get("id_original"),
                "detailed_prompt": row.get("detailed_prompt"),
                "hint_included": row.get("hint_included"),
                "name": row.get("name"),
                "category": row.get("category"),
                "prompt": prompt,
                "target_functions": target_functions,
                "tool_names": target_functions,
                "grading_function": row.get("grading_function"),
                "split": row.get("split") or self.default_split,
                "mode": self.mode,
            },
        }

    def _passes_adapter_filters(self, row: dict[str, Any]) -> bool:
        ids = self._behavior_id_list()
        if ids and str(row.get("id")) not in ids:
            return False
        detailed = _coerce_bool(self.detailed_behaviors)
        if detailed is not None and bool(row.get("detailed_prompt")) != detailed:
            return False
        hinted = _coerce_bool(self.hint_included)
        if hinted is not None and bool(row.get("hint_included")) != hinted:
            return False
        return True

    def _behavior_id_list(self) -> set[str]:
        if self.behavior_ids is None:
            return set()
        if isinstance(self.behavior_ids, str):
            return {part.strip() for part in self.behavior_ids.split(",") if part.strip()}
        return {str(item).strip() for item in self.behavior_ids if str(item).strip()}

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        _ = task
        return {"scoring": "agentharm_refusal", "mode": self.mode}
