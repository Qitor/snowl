"""First benchmark adapter: JSONL benchmark loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class JsonlBenchmarkAdapter:
    """Loads a JSONL benchmark file into a Task with homogeneous schema."""

    dataset_path: str
    name: str = "jsonl"
    description: str = "Generic JSONL benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    input_field: str = "input"
    target_field: str = "target"
    id_field: str = "id"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def list_splits(self) -> list[str]:
        path = Path(self.dataset_path)
        if not path.exists():
            raise SnowlValidationError(f"JSONL benchmark file not found: {path}")

        splits: set[str] = set()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                split = str(row.get(self.split_field, self.default_split))
                splits.add(split)

        return sorted(splits) if splits else [self.default_split]

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]:
        path = Path(self.dataset_path)
        if not path.exists():
            raise SnowlValidationError(f"JSONL benchmark file not found: {path}")

        selected: list[dict[str, Any]] = []
        filters = filters or {}

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)

                row_split = str(row.get(self.split_field, self.default_split))
                if row_split != split:
                    continue

                matched = True
                for key, expected in filters.items():
                    if row.get(key) != expected:
                        matched = False
                        break
                if not matched:
                    continue

                sample = {
                    "id": row.get(self.id_field) or f"{split}-{len(selected)+1}",
                    "input": row.get(self.input_field, ""),
                    "target": row.get(self.target_field),
                    "metadata": {k: v for k, v in row.items() if k not in {self.input_field, self.target_field}},
                }
                selected.append(sample)

                if limit is not None and len(selected) >= limit:
                    break

        if not selected:
            raise SnowlValidationError(
                f"No benchmark samples loaded for split='{split}' in {path}."
            )

        task = Task(
            task_id=f"{self.name}:{split}",
            env_spec=EnvSpec(env_type="local"),
            sample_iter_factory=lambda: iter(selected),
            metadata={
                "benchmark": self.name,
                "split": split,
                "dataset_path": str(path),
            },
        )
        return [task]
