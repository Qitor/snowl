"""Agent-SafetyBench benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path, read_json_array
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "Agent-SafetyBench",
        "data",
        "released_data.json",
    )


@dataclass(frozen=True)
class AgentSafetyBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "agentsafetybench"
    description: str = "Agent-SafetyBench benchmark adapter."
    default_split: str = "official"

    def list_splits(self) -> list[str]:
        return [self.default_split]

    def _iter_rows(self) -> list[dict[str, Any]]:
        data = read_json_array(
            self.dataset_path,
            not_found_message="Agent-SafetyBench dataset file not found",
            invalid_message="Agent-SafetyBench dataset must be a JSON array",
        )
        rows = [dict(item) for item in data if isinstance(item, dict)]
        if not rows:
            raise SnowlValidationError(
                f"No Agent-SafetyBench rows found in dataset: {self.dataset_path}"
            )
        return rows

    def _validate_split_request(self, split: str) -> None:
        if split != self.default_split:
            raise SnowlValidationError(
                f"Agent-SafetyBench only exposes split '{self.default_split}', got '{split}'."
            )

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = (row, row_index)
        return self.default_split

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, selected_count)
        instruction = str(row.get("instruction") or "").strip()
        if not instruction:
            return None
        sample_id = f"agentsafetybench-{row.get('id')}"
        return {
            "id": sample_id,
            "input": instruction,
            "metadata": {
                "benchmark": self.name,
                "split": row_split,
                "case": dict(row),
                "case_id": row.get("id"),
                "risks": list(row.get("risks") or []),
                "failure_modes": str(row.get("failure_modes") or ""),
                "fulfillable": row.get("fulfillable"),
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(self.dataset_path),
            "case_count": selected_count,
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No Agent-SafetyBench samples loaded for split='{split}' in {self.dataset_path}."
