"""TerminalBench benchmark adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    root = Path(__file__).resolve().parents[3]
    return str(root / "references" / "terminal-bench" / "original-tasks")

def _resolve_compose_file(task_dir: Path) -> Path | None:
    for name in ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml"):
        p = task_dir / name
        if p.exists():
            return p
    return None


@dataclass(frozen=True)
class TerminalBenchBenchmarkAdapter:
    dataset_path: str = _default_dataset_path()
    name: str = "terminalbench"
    description: str = "Terminal-Bench benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"

    @property
    def info(self) -> BenchmarkInfo:
        return BenchmarkInfo(name=self.name, description=self.description)

    def _task_dirs(self) -> list[Path]:
        root = Path(self.dataset_path)
        if not root.exists():
            raise SnowlValidationError(f"TerminalBench dataset path not found: {root}")
        out: list[Path] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if (child / "task.yaml").exists():
                out.append(child)
        if not out:
            raise SnowlValidationError(f"No task directories with task.yaml found in {root}")
        return out

    def _load_task_yaml(self, path: Path) -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        return data

    def list_splits(self) -> list[str]:
        splits: set[str] = set()
        for task_dir in self._task_dirs():
            data = self._load_task_yaml(task_dir / "task.yaml")
            split = str(data.get(self.split_field) or self.default_split).strip()
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
        selected: list[dict[str, Any]] = []
        for task_dir in self._task_dirs():
            task_id = task_dir.name
            data = self._load_task_yaml(task_dir / "task.yaml")
            row_split = str(data.get(self.split_field) or self.default_split).strip() or self.default_split
            if row_split != split:
                continue

            row = {
                "task_id": task_id,
                "difficulty": data.get("difficulty"),
                "category": data.get("category"),
                "parser_name": data.get("parser_name", "pytest"),
            }
            matched = True
            for key, expected in filters.items():
                value = row.get(key, data.get(key))
                if str(value) != str(expected):
                    matched = False
                    break
            if not matched:
                continue

            instruction = str(data.get("instruction") or "").strip()
            if not instruction:
                continue

            digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:10]
            compose_path = _resolve_compose_file(task_dir)
            sample = {
                "id": f"tb-{task_id}-{digest}",
                "input": instruction,
                "metadata": {
                    "task_id": task_id,
                    "instruction": instruction,
                    "split": row_split,
                    "difficulty": data.get("difficulty"),
                    "category": data.get("category"),
                    "tags": list(data.get("tags") or []),
                    "parser_name": str(data.get("parser_name", "pytest")),
                    "max_agent_timeout_sec": data.get("max_agent_timeout_sec"),
                    "max_test_timeout_sec": data.get("max_test_timeout_sec"),
                    "task_root": str(task_dir),
                    "task_yaml_path": str(task_dir / "task.yaml"),
                    "run_tests_path": str(task_dir / "run-tests.sh"),
                    "docker_compose_path": (str(compose_path) if compose_path is not None else ""),
                    "tests_dir": str(task_dir / "tests"),
                },
            }
            selected.append(sample)
            if limit is not None and len(selected) >= limit:
                break

        if not selected:
            raise SnowlValidationError(
                f"No TerminalBench samples loaded for split='{split}' in {self.dataset_path}."
            )

        task = Task(
            task_id=f"{self.name}:{split}",
            env_spec=EnvSpec(
                env_type="terminal",
                provided_ops=(
                    "process.run",
                    "terminal.exec",
                    "terminal.send_keys",
                    "terminal.capture",
                    "terminal.wait",
                ),
            ),
            sample_iter_factory=lambda: iter(selected),
            metadata={
                "benchmark": self.name,
                "split": split,
                "dataset_path": str(Path(self.dataset_path)),
                "task_count": len(selected),
            },
        )
        return [task]
