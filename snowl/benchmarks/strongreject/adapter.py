"""StrongReject benchmark adapter."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "references" / "strongreject" / "strongreject_dataset" / "strongreject_small_dataset.csv")


@dataclass(frozen=True)
class StrongRejectBenchmarkAdapter:
    dataset_path: str = _default_dataset_path()
    name: str = "strongreject"
    description: str = "StrongReject benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    prompt_field: str = "forbidden_prompt"
    id_field: str = "id"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def list_splits(self) -> list[str]:
        path = Path(self.dataset_path)
        if not path.exists():
            raise SnowlValidationError(f"StrongReject dataset file not found: {path}")

        splits: set[str] = set()
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                split = str(row.get(self.split_field) or self.default_split).strip()
                splits.add(split or self.default_split)
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
            raise SnowlValidationError(f"StrongReject dataset file not found: {path}")

        selected: list[dict[str, Any]] = []
        filters = filters or {}
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=1):
                row_split = str(row.get(self.split_field) or self.default_split).strip() or self.default_split
                if row_split != split:
                    continue

                matched = True
                for key, expected in filters.items():
                    if str(row.get(key, "")) != str(expected):
                        matched = False
                        break
                if not matched:
                    continue

                prompt = str(row.get(self.prompt_field) or "").strip()
                if not prompt:
                    continue

                sample_id = str(row.get(self.id_field) or "").strip()
                if not sample_id:
                    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
                    sample_id = f"sr-{row_idx:06d}-{digest}"

                sample = {
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
                selected.append(sample)
                if limit is not None and len(selected) >= limit:
                    break

        if not selected:
            raise SnowlValidationError(
                f"No StrongReject samples loaded for split='{split}' in {path}."
            )

        task = Task(
            task_id=f"{self.name}:{split}",
            env_spec=EnvSpec(env_type="local"),
            sample_iter_factory=lambda: iter(selected),
            metadata={
                "benchmark": self.name,
                "split": split,
                "dataset_path": str(path),
                "scoring": "strongreject",
            },
        )
        return [task]

