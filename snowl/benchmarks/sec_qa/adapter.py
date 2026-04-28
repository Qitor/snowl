"""SecQA benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import HFDatasetAsset, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


_SOURCE = "zefang-liu/secqa"
_REVISION = "d00a07484283be5602e2bae36dbefdaaf555a9fb"
_VARIANTS = {"secqa_v1": "sec_qa_v1", "secqa_v2": "sec_qa_v2"}
_SPLITS = ("test", "dev")
_LABELS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class SecQABenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    variant: str = "secqa_v1"
    rows: list[dict[str, Any]] | None = None
    name: str = "sec_qa_v1"
    description: str = "SecQA multiple-choice benchmark adapter."
    default_split: str = "test"

    def __post_init__(self) -> None:
        if self.variant not in _VARIANTS:
            valid = ", ".join(sorted(_VARIANTS))
            raise SnowlValidationError(
                f"Unsupported SecQA variant '{self.variant}'. Valid variants: {valid}."
            )
        object.__setattr__(self, "name", _VARIANTS[self.variant])

    def benchmark_info(self) -> BenchmarkInfo:
        display = self.name.replace("_", " ").title().replace("Qa", "QA")
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name=display,
            short_description=f"{display} cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sec_qa",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "question_preview": str(row.get("Question") or row.get("question") or "")[:200],
            "choices_count": 4,
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        _ = task
        return {
            "scoring": "accuracy",
            "variant": self.variant,
            "source": _SOURCE,
            "revision": _REVISION,
        }

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return list(self.rows)
        rows: list[dict[str, Any]] = []
        for split in _SPLITS:
            split_rows = HFDatasetAsset(
                source=_SOURCE,
                revision=_REVISION,
                split=split,
                name=self.variant,
                cache_tag=f"sec_qa/{self.variant}",
            ).load_rows()
            for row in split_rows:
                row.setdefault("split", split)
                rows.append(row)
        return rows

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
        _ = selected_count
        question = str(row.get("Question") or row.get("question") or "").strip()
        target = str(row.get("Answer") or row.get("answer") or "").strip().upper()
        if not question or not target:
            return None

        choices = [str(row.get(label) or row.get(label.lower()) or "").strip() for label in _LABELS]
        if not all(choices):
            return None
        option_lines = [f"{label}. {choice}" for label, choice in zip(_LABELS, choices)]
        formatted_input = f"{question}\n\n" + "\n".join(option_lines)
        formatted_input += "\n\nAnswer with the letter of the correct choice."
        sample_id = str(row.get("id") or "").strip()
        if not sample_id:
            sample_id = stable_benchmark_id("secqa", self.variant, row_split, row_index, question)

        return {
            "id": sample_id,
            "input": formatted_input,
            "metadata": {
                "choices": choices,
                "choice_labels": list(_LABELS),
                "answer": target,
                "target": target,
                "split": row_split,
                "variant": self.variant,
                "source_revision": _REVISION,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
