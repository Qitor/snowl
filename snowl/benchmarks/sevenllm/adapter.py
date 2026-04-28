"""SEVENLLM multiple-choice benchmark adapter."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import HFSnapshotFileAsset, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError


_SOURCE = "Multilingual-Multimodal-NLP/SEVENLLM-Dataset"
_REVISION = "1de23ce55cadc984d3f3a7b52c4035a68c6cd5b0"
_LABELS = ("A", "B", "C", "D")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class SevenLLMMCQBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    language: str = "en"
    rows: list[dict[str, Any]] | None = None
    name: str = "sevenllm_mcq_en"
    description: str = "SEVENLLM multiple-choice benchmark adapter."
    default_split: str = "test"

    def __post_init__(self) -> None:
        lang = self.language.lower().strip()
        if lang not in {"en", "zh"}:
            raise SnowlValidationError("SEVENLLM MCQ language must be 'en' or 'zh'.")
        object.__setattr__(self, "language", lang)
        object.__setattr__(self, "name", f"sevenllm_mcq_{lang}")

    def benchmark_info(self) -> BenchmarkInfo:
        display = "SEVENLLM MCQ EN" if self.language == "en" else "SEVENLLM MCQ ZH"
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name=display,
            short_description=f"{display} cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sevenllm",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity", self.language],
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        instruction = row.get("instruction", {})
        question = instruction.get("question", "") if isinstance(instruction, dict) else ""
        return {
            "id": row.get("id", ""),
            "question_preview": str(question)[:200],
            "choices_count": 4,
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        _ = task
        return {
            "scoring": "accuracy",
            "language": self.language,
            "source": _SOURCE,
            "revision": _REVISION,
        }

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return list(self.rows)
        path = HFSnapshotFileAsset(
            source=_SOURCE,
            revision=_REVISION,
            relative_path="test.jsonl",
            allow_patterns=("test.jsonl",),
            cache_tag="sevenllm",
        ).resolve_path()
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
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
        _ = (row_index, selected_count)
        instruction = row.get("instruction")
        if not isinstance(instruction, dict):
            return None
        question = str(instruction.get("question") or "").strip()
        choice_map = instruction.get("choice")
        if not question or not isinstance(choice_map, dict):
            return None
        context = str(row.get("input") or "").strip()
        row_language = "zh" if _CJK_RE.search(f"{question}\n{context}") else "en"
        if row_language != self.language:
            return None

        target = str(row.get("output") or "").strip().upper()
        choices = [str(choice_map.get(label) or "").strip() for label in _LABELS]
        if not target or not all(choices):
            return None
        option_lines = [f"{label}. {choice}" for label, choice in zip(_LABELS, choices)]
        formatted_parts = [question]
        if context:
            formatted_parts.append(context)
        formatted_parts.append("\n".join(option_lines))
        formatted_input = "\n\n".join(formatted_parts)
        formatted_input += "\n\nAnswer with the letter of the correct choice."
        sample_id = str(row.get("id") or "").strip()
        if not sample_id:
            sample_id = stable_benchmark_id("sevenllm", self.language, question, context)

        return {
            "id": sample_id,
            "input": formatted_input,
            "metadata": {
                "choices": choices,
                "choice_labels": list(_LABELS),
                "answer": target,
                "target": target,
                "category": row.get("category"),
                "cot": row.get("cot"),
                "format": "mcq",
                "language": self.language,
                "split": row_split,
                "source_revision": _REVISION,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
