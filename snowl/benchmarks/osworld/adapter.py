"""OSWorld benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, SandboxSpec, Task
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "references" / "OSWorld" / "evaluation_examples")


@dataclass(frozen=True)
class OSWorldBenchmarkAdapter:
    dataset_path: str = _default_dataset_path()
    name: str = "osworld"
    description: str = "OSWorld benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    test_all_meta_path: str = "test_all.json"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def _dataset_root(self) -> Path:
        root = Path(self.dataset_path)
        if not root.exists():
            raise SnowlValidationError(f"OSWorld dataset path not found: {root}")
        return root

    def _test_all(self) -> dict[str, list[str]]:
        root = self._dataset_root()
        path = root / self.test_all_meta_path
        if not path.exists():
            raise SnowlValidationError(f"OSWorld test_all file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SnowlValidationError(f"OSWorld test_all format invalid: {path}")
        out: dict[str, list[str]] = {}
        for domain, ids in data.items():
            if not isinstance(ids, list):
                continue
            out[str(domain)] = [str(x) for x in ids]
        return out

    def list_splits(self) -> list[str]:
        splits: set[str] = set()
        root = self._dataset_root()
        for domain, ids in self._test_all().items():
            for example_id in ids:
                file_path = root / "examples" / domain / f"{example_id}.json"
                if not file_path.exists():
                    continue
                example = json.loads(file_path.read_text(encoding="utf-8"))
                split = str(example.get(self.split_field) or self.default_split).strip()
                splits.add(split or self.default_split)
        return sorted(splits) if splits else [self.default_split]

    def load_tasks(
        self,
        *,
        split: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Task]:
        filters = filters or {}
        root = self._dataset_root()
        selected: list[dict[str, Any]] = []

        for domain, ids in self._test_all().items():
            for example_id in ids:
                file_path = root / "examples" / domain / f"{example_id}.json"
                if not file_path.exists():
                    continue
                example = json.loads(file_path.read_text(encoding="utf-8"))
                row_split = str(example.get(self.split_field) or self.default_split).strip() or self.default_split
                if row_split != split:
                    continue
                matched = True
                for key, expected in filters.items():
                    if key == "domain":
                        value = domain
                    elif key == "example_id":
                        value = example_id
                    else:
                        value = example.get(key)
                    if str(value) != str(expected):
                        matched = False
                        break
                if not matched:
                    continue

                instruction = str(example.get("instruction") or "").strip()
                if not instruction:
                    continue
                metadata = {
                    "domain": domain,
                    "example_id": example_id,
                    "osworld_task_id": str(example.get("id") or example_id),
                    "split": row_split,
                    "instruction": instruction,
                    "snapshot": example.get("snapshot"),
                    "proxy": bool(example.get("proxy", False)),
                    "related_apps": list(example.get("related_apps") or []),
                    "config": list(example.get("config") or []),
                    "trajectory": list(example.get("trajectory") or []),
                    "evaluator": example.get("evaluator"),
                    "source": example.get("source"),
                    "example_path": str(file_path),
                    "task_config": dict(example),
                }
                selected.append(
                    {
                        "id": f"osw-{domain}-{example_id}",
                        "input": instruction,
                        "metadata": metadata,
                    }
                )
                if limit is not None and len(selected) >= limit:
                    break
            if limit is not None and len(selected) >= limit:
                break

        if not selected:
            raise SnowlValidationError(
                f"No OSWorld samples loaded for split='{split}' in {root}."
            )

        task = Task(
            task_id=f"{self.name}:{split}",
            env_spec=EnvSpec(
                env_type="gui",
                provided_ops=(
                    "gui.action",
                    "gui.click",
                    "gui.type",
                    "gui.key",
                    "gui.scroll",
                    "gui.observe",
                    "gui.wait",
                    "gui.terminate",
                ),
                sandbox_spec=SandboxSpec(
                    provider="docker",
                    image="happysixd/osworld-docker",
                    metadata={"benchmark": "osworld"},
                ),
            ),
            sample_iter_factory=lambda: iter(selected),
            metadata={
                "benchmark": self.name,
                "split": split,
                "dataset_path": str(root),
                "test_all_meta_path": str(root / self.test_all_meta_path),
            },
        )
        return [task]

