"""Adapter layer that maps `terminalbench` source datasets into Snowl task/sample contracts.

Framework role:
- Owns benchmark-specific split/filter/sample-id logic and metadata extraction.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry/bench orchestration and executed through the shared eval pipeline.
- Key top-level symbols in this file: `_default_dataset_path`, `_resolve_compose_file`, `TerminalBenchBenchmarkAdapter`.

Change guardrails:
- Preserve deterministic sample identity and metadata contract; scorer/runtime layers depend on it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import (
    default_reference_path,
    ensure_path_exists,
    read_yaml_mapping,
)
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "terminal-bench",
        "original-tasks",
    )


def _resolve_compose_file(task_dir: Path) -> Path | None:
    for name in ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml"):
        p = task_dir / name
        if p.exists():
            return p
    return None


@dataclass(frozen=True)
class TerminalBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "terminalbench"
    description: str = "Terminal-Bench benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"

    def _task_dirs(self) -> list[Path]:
        root = ensure_path_exists(
            self.dataset_path,
            not_found_message="TerminalBench dataset path not found",
        )
        out: list[Path] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if (child / "task.yaml").exists():
                out.append(child)
        if not out:
            raise SnowlValidationError(f"No task directories with task.yaml found in {root}")
        return out

    def _iter_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for task_dir in self._task_dirs():
            data = read_yaml_mapping(task_dir / "task.yaml")
            rows.append({"task_dir": task_dir, "data": data})
        return rows

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        data = dict(row.get("data") or {})
        return str(data.get(self.split_field) or self.default_split)

    def _row_filter_value(self, row: dict[str, Any], key: str) -> Any:
        data = dict(row.get("data") or {})
        task_dir = Path(row.get("task_dir"))
        if key == "task_id":
            return task_dir.name
        if key == "difficulty":
            return data.get("difficulty")
        if key == "category":
            return data.get("category")
        if key == "parser_name":
            return data.get("parser_name", "pytest")
        return data.get(key)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, selected_count)
        task_dir = Path(row.get("task_dir"))
        data = dict(row.get("data") or {})
        task_id = task_dir.name
        instruction = str(data.get("instruction") or "").strip()
        if not instruction:
            return None

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
        return sample

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(
            env_type="terminal",
            provided_ops=(
                "process.run",
                "terminal.exec",
                "terminal.send_keys",
                "terminal.capture",
                "terminal.wait",
            ),
        )

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(Path(self.dataset_path)),
            "task_count": selected_count,
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No TerminalBench samples loaded for split='{split}' in {self.dataset_path}."
