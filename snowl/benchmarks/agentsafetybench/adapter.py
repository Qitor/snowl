"""Agent-SafetyBench benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "references" / "Agent-SafetyBench" / "data" / "released_data.json")


@dataclass(frozen=True)
class AgentSafetyBenchBenchmarkAdapter:
    dataset_path: str = _default_dataset_path()
    name: str = "agentsafetybench"
    description: str = "Agent-SafetyBench benchmark adapter."
    default_split: str = "official"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def _load_rows(self) -> list[dict[str, Any]]:
        path = Path(self.dataset_path)
        if not path.exists():
            raise SnowlValidationError(f"Agent-SafetyBench dataset file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SnowlValidationError(f"Agent-SafetyBench dataset must be a JSON array: {path}")
        rows = [dict(item) for item in data if isinstance(item, dict)]
        if not rows:
            raise SnowlValidationError(f"No Agent-SafetyBench rows found in dataset: {path}")
        return rows

    def list_splits(self) -> list[str]:
        return [self.default_split]

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]:
        if split != self.default_split:
            raise SnowlValidationError(
                f"Agent-SafetyBench only exposes split '{self.default_split}', got '{split}'."
            )
        filters = filters or {}
        selected: list[dict[str, Any]] = []
        for row in self._load_rows():
            matched = True
            for key, expected in filters.items():
                value = row.get(key)
                if str(value) != str(expected):
                    matched = False
                    break
            if not matched:
                continue
            instruction = str(row.get("instruction") or "").strip()
            if not instruction:
                continue
            sample_id = f"agentsafetybench-{row.get('id')}"
            selected.append(
                {
                    "id": sample_id,
                    "input": instruction,
                    "metadata": {
                        "benchmark": self.name,
                        "split": split,
                        "case": dict(row),
                        "case_id": row.get("id"),
                        "risks": list(row.get("risks") or []),
                        "failure_modes": str(row.get("failure_modes") or ""),
                        "fulfillable": row.get("fulfillable"),
                    },
                }
            )
            if limit is not None and len(selected) >= limit:
                break

        if not selected:
            raise SnowlValidationError(
                f"No Agent-SafetyBench samples loaded for split='{split}' in {self.dataset_path}."
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
