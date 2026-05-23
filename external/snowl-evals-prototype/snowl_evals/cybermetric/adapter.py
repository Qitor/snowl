"""CyberMetric benchmark adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import DirectURLAsset, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


_REVISION = "205262cdf5022ba890e792efd176fb19d42913fa"
_BASE_URL = "https://raw.githubusercontent.com/cybermetric/CyberMetric"
_DATASETS: dict[str, dict[str, str]] = {
    "CyberMetric-80": {
        "name": "cybermetric_80",
        "sha256": "1624aeecc54761198bff4828442ce4a10de6cb87c9da3298088b34ae11e15ba0",
    },
    "CyberMetric-500": {
        "name": "cybermetric_500",
        "sha256": "036747c989da9f38f39a6b33fa2d5ab14147c928df0274217bbecab20be88faa",
    },
    "CyberMetric-2000": {
        "name": "cybermetric_2000",
        "sha256": "3ccc4d425bc4e74d27e0e9790d62369e4626e325d2b661d851c61b1648a0cd4a",
    },
    "CyberMetric-10000": {
        "name": "cybermetric_10000",
        "sha256": "4e35bb62c73b60bd27e54512b2ace6f9286ff2921a45a3d5fe2da22401e04bbb",
    },
}


@dataclass(frozen=True)
class CyberMetricBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_name: str = "CyberMetric-80"
    rows: list[dict[str, Any]] | None = None
    name: str = "cybermetric_80"
    description: str = "CyberMetric multiple-choice benchmark adapter."
    default_split: str = "test"

    def __post_init__(self) -> None:
        dataset_meta = _DATASETS.get(self.dataset_name)
        if dataset_meta is None:
            valid = ", ".join(sorted(_DATASETS))
            raise SnowlValidationError(
                f"Unsupported CyberMetric dataset '{self.dataset_name}'. Valid datasets: {valid}."
            )
        object.__setattr__(self, "name", dataset_meta["name"])

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name=self.dataset_name,
            short_description=f"{self.dataset_name} cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="cybermetric",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "question_preview": str(row.get("question", ""))[:200],
            "choices_count": len(row.get("answers", {}))
            if isinstance(row.get("answers"), dict)
            else 0,
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        _ = task
        return {
            "scoring": "accuracy",
            "dataset_name": self.dataset_name,
            "source": "cybermetric/CyberMetric",
            "revision": _REVISION,
        }

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return list(self.rows)
        dataset_meta = _DATASETS[self.dataset_name]
        url = f"{_BASE_URL}/{_REVISION}/{self.dataset_name}-v1.json"
        path = DirectURLAsset(
            url=url,
            sha256=dataset_meta["sha256"],
            cache_name=f"cybermetric/{self.dataset_name}-v1.json",
        ).resolve_path()
        raw = json.loads(path.read_text(encoding="utf-8"))
        questions = raw.get("questions") if isinstance(raw, dict) else raw
        if not isinstance(questions, list):
            raise SnowlValidationError(f"CyberMetric asset has unexpected shape: {path}")
        return [row for row in questions if isinstance(row, dict)]

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split") or "test")

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = (row_index, selected_count)
        question = str(row.get("question") or "").strip()
        answers = row.get("answers")
        target = str(row.get("solution") or row.get("answer") or "").strip().upper()
        if not question or not isinstance(answers, dict) or not target:
            return None

        items = [(str(label).strip().upper(), str(value)) for label, value in answers.items()]
        labels = [label for label, _ in items]
        choices = [value for _, value in items]
        option_lines = [f"{label}. {value}" for label, value in items]
        formatted_input = f"{question}\n\n" + "\n".join(option_lines)
        formatted_input += "\n\nAnswer with the letter of the correct choice."
        sample_id = str(row.get("id") or "").strip()
        if not sample_id:
            sample_id = stable_benchmark_id("cybermetric", self.dataset_name, question)

        return {
            "id": sample_id,
            "input": formatted_input,
            "metadata": {
                "choices": choices,
                "choice_labels": labels,
                "answer": target,
                "target": target,
                "split": row_split,
                "dataset_name": self.dataset_name,
                "source_revision": _REVISION,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
