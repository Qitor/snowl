"""Adapter layer that maps `toolemu` source datasets into Snowl task/sample contracts.

Framework role:
- Owns benchmark-specific split/filter/sample-id logic and metadata extraction.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry/bench orchestration and executed through the shared eval pipeline.
- Key top-level symbols in this file: `_default_dataset_path`, `_case_split`, `ToolEmuBenchmarkAdapter`.

Change guardrails:
- Preserve deterministic sample identity and metadata contract; scorer/runtime layers depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path, matches_filters, read_json_array
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "ToolEmu",
        "assets",
        "all_cases.json",
    )


def _case_split(case: Mapping[str, Any], default_split: str) -> str:
    explicit = str(case.get("split") or "").strip()
    if explicit:
        return explicit
    name = str(case.get("name") or "").strip()
    if "_" in name:
        prefix = name.split("_", 1)[0].strip()
        if prefix:
            return prefix
    return default_split


@dataclass(frozen=True)
class ToolEmuBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "toolemu"
    description: str = "ToolEmu benchmark adapter."
    default_split: str = "official"

    def _iter_rows(self) -> list[dict[str, Any]]:
        data = read_json_array(
            self.dataset_path,
            not_found_message="ToolEmu dataset file not found",
            invalid_message="ToolEmu dataset must be a JSON array",
        )
        rows: list[dict[str, Any]] = []
        for row in data:
            if isinstance(row, dict):
                rows.append(dict(row))
        if not rows:
            raise SnowlValidationError(f"No ToolEmu cases found in dataset: {self.dataset_path}")
        return rows

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return _case_split(row, self.default_split)

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        toolkits = [str(x) for x in (row.get("Toolkits") or []) if str(x).strip()]
        return matches_filters(
            filters=filters,
            resolver=lambda key: toolkits if key == "toolkit" else row.get(key, ""),
            stringify=True,
            comparators={
                "toolkit": lambda value, expected: str(expected) in [str(x) for x in (value or [])],
            },
        )

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        case_name = str(row.get("name") or "").strip() or f"{self.name}_{row_index - 1}"
        user_instruction = str(row.get("User Instruction") or "").strip()
        if not user_instruction:
            return None
        toolkits = [str(x) for x in (row.get("Toolkits") or []) if str(x).strip()]
        metadata = {
            "name": case_name,
            "split": row_split,
            "toolkits": toolkits,
            "underspecifications": dict(row.get("Underspecifications") or {}),
            "expected_achievements": list(row.get("Expected Achievements") or []),
            "potential_risky_outcomes": list(row.get("Potential Risky Outcomes") or []),
            "potential_risky_actions": list(row.get("Potential Risky Actions") or []),
            "case": dict(row),
        }
        return {
            "id": f"toolemu-{case_name}",
            "input": user_instruction,
            "metadata": metadata,
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
        return f"No ToolEmu samples loaded for split='{split}' in {self.dataset_path}."
