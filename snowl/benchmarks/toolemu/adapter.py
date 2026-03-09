"""ToolEmu benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "references" / "ToolEmu" / "assets" / "all_cases.json")


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
class ToolEmuBenchmarkAdapter:
    dataset_path: str = _default_dataset_path()
    name: str = "toolemu"
    description: str = "ToolEmu benchmark adapter."
    default_split: str = "official"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def _load_cases(self) -> list[dict[str, Any]]:
        path = Path(self.dataset_path)
        if not path.exists():
            raise SnowlValidationError(f"ToolEmu dataset file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SnowlValidationError(f"ToolEmu dataset must be a JSON array: {path}")
        rows: list[dict[str, Any]] = []
        for row in data:
            if isinstance(row, dict):
                rows.append(dict(row))
        if not rows:
            raise SnowlValidationError(f"No ToolEmu cases found in dataset: {path}")
        return rows

    def list_splits(self) -> list[str]:
        splits: set[str] = set()
        for case in self._load_cases():
            splits.add(_case_split(case, self.default_split))
        return sorted(splits) if splits else [self.default_split]

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]:
        rows = self._load_cases()
        filters = filters or {}
        selected: list[dict[str, Any]] = []

        for idx, case in enumerate(rows):
            row_split = _case_split(case, self.default_split)
            if row_split != split:
                continue

            toolkits = [str(x) for x in (case.get("Toolkits") or []) if str(x).strip()]
            matched = True
            for key, expected in filters.items():
                if key == "toolkit":
                    if str(expected) not in toolkits:
                        matched = False
                        break
                    continue
                if str(case.get(key, "")) != str(expected):
                    matched = False
                    break
            if not matched:
                continue

            case_name = str(case.get("name") or "").strip() or f"{self.name}_{idx}"
            user_instruction = str(case.get("User Instruction") or "").strip()
            if not user_instruction:
                continue
            metadata = {
                "name": case_name,
                "split": row_split,
                "toolkits": toolkits,
                "underspecifications": dict(case.get("Underspecifications") or {}),
                "expected_achievements": list(case.get("Expected Achievements") or []),
                "potential_risky_outcomes": list(case.get("Potential Risky Outcomes") or []),
                "potential_risky_actions": list(case.get("Potential Risky Actions") or []),
                "case": dict(case),
            }
            selected.append(
                {
                    "id": f"toolemu-{case_name}",
                    "input": user_instruction,
                    "metadata": metadata,
                }
            )
            if limit is not None and len(selected) >= limit:
                break

        if not selected:
            raise SnowlValidationError(
                f"No ToolEmu samples loaded for split='{split}' in {self.dataset_path}."
            )

        task = Task(
            task_id=f"{self.name}:{split}",
            env_spec=EnvSpec(env_type="local"),
            sample_iter_factory=lambda: iter(selected),
            metadata={
                "benchmark": self.name,
                "split": split,
                "dataset_path": str(Path(self.dataset_path)),
                "case_count": len(selected),
            },
        )
        return [task]
