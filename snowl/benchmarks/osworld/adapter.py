"""OSWorld benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import (
    default_reference_path,
    ensure_path_exists,
    read_json_object,
)
from snowl.core import EnvSpec, SandboxSpec


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "OSWorld",
        "evaluation_examples",
    )


@dataclass(frozen=True)
class OSWorldBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "osworld"
    description: str = "OSWorld benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    test_all_meta_path: str = "test_all.json"

    def _dataset_root(self) -> Path:
        return ensure_path_exists(
            self.dataset_path,
            not_found_message="OSWorld dataset path not found",
        )

    def _test_all(self) -> dict[str, list[str]]:
        root = self._dataset_root()
        data = read_json_object(
            root / self.test_all_meta_path,
            not_found_message="OSWorld test_all file not found",
            invalid_message="OSWorld test_all format invalid",
        )
        out: dict[str, list[str]] = {}
        for domain, ids in data.items():
            if not isinstance(ids, list):
                continue
            out[str(domain)] = [str(x) for x in ids]
        return out

    def _iter_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        root = self._dataset_root()
        for domain, ids in self._test_all().items():
            for example_id in ids:
                file_path = root / "examples" / domain / f"{example_id}.json"
                if not file_path.exists():
                    continue
                example = read_json_object(
                    file_path,
                    not_found_message="OSWorld example file not found",
                    invalid_message="OSWorld example format invalid",
                )
                rows.append(
                    {
                        "domain": domain,
                        "example_id": example_id,
                        "file_path": file_path,
                        "example": example,
                    }
                )
        return rows

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        example = dict(row.get("example") or {})
        return str(example.get(self.split_field) or self.default_split)

    def _row_filter_value(self, row: dict[str, Any], key: str) -> Any:
        if key == "domain":
            return row.get("domain")
        if key == "example_id":
            return row.get("example_id")
        example = dict(row.get("example") or {})
        return example.get(key)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, selected_count)
        domain = str(row.get("domain"))
        example_id = str(row.get("example_id"))
        file_path = row.get("file_path")
        example = dict(row.get("example") or {})

        instruction = str(example.get("instruction") or "").strip()
        if not instruction:
            return None

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
        return {
            "id": f"osw-{domain}-{example_id}",
            "input": instruction,
            "metadata": metadata,
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(
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
        )

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        _ = selected_count
        root = self._dataset_root()
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(root),
            "test_all_meta_path": str(root / self.test_all_meta_path),
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No OSWorld samples loaded for split='{split}' in {self._dataset_root()}."
