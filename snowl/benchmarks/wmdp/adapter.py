"""WMDP (Weapons of Mass Destruction Proxy) benchmark adapter.

Maps WMDP multiple-choice question datasets into Snowl task/sample contracts.
Supports both cyber (wmdp-cyber) and chemistry (wmdp-chem) variants via the
`variant` field.

Framework role:
- Owns benchmark-specific row iteration, split logic, and MCQ sample formatting.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry and executed through the shared eval pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import HFDatasetAsset, default_reference_path, stable_benchmark_id
from snowl.core import EnvSpec

# HuggingFace dataset (same as inspect_evals reference).
_HF_DATASET_PATH = "cais/wmdp"
_HF_DATASET_REVISION = "7125571f22f032c56415e7980f48d877dd830ff8"


def _default_cyber_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "wmdp",
        "wmdp-cyber",
        "wmdp_cyber.jsonl",
    )


def _default_chem_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "wmdp",
        "wmdp-chem",
        "wmdp_chem.jsonl",
    )


_VARIANT_METADATA = {
    "wmdp-cyber": {
        "domain": "cyber_offense",
        "benchmark_type": "capability",
        "family": "wmdp",
        "primary_metric": "accuracy",
        "higher_is_better": True,
        "sample_preview_mode": "qa",
        "dashboard_tags": ["mcq", "cybersecurity"],
    },
    "wmdp-chem": {
        "domain": "chemical_risks",
        "benchmark_type": "capability",
        "family": "wmdp",
        "primary_metric": "accuracy",
        "higher_is_better": True,
        "sample_preview_mode": "qa",
        "dashboard_tags": ["mcq", "chemistry"],
    },
}


def _load_local_jsonl(path: str) -> list[dict[str, Any]]:
    """Try loading rows from a local JSONL file."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            import json
            rows.append(json.loads(line))
    return rows


def _load_hf_rows(variant: str) -> list[dict[str, Any]]:
    """Load rows from HuggingFace cais/wmdp dataset."""
    hf_name = variant  # "wmdp-cyber" or "wmdp-chem"
    return HFDatasetAsset(
        source=_HF_DATASET_PATH,
        revision=_HF_DATASET_REVISION,
        split="test",
        name=hf_name,
        cache_tag=f"wmdp-{variant}",
    ).load_rows()


@dataclass(frozen=True)
class WMDPBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    variant: str = "wmdp-cyber"
    name: str = "wmdp-cyber"
    description: str = "WMDP-Cyber benchmark adapter."
    default_split: str = "test"

    def __post_init__(self) -> None:
        if not self.dataset_path:
            if self.variant == "wmdp-chem":
                object.__setattr__(self, "dataset_path", _default_chem_dataset_path())
            else:
                object.__setattr__(self, "dataset_path", _default_cyber_dataset_path())
            object.__setattr__(self, "name", self.variant)
            if self.variant == "wmdp-chem":
                object.__setattr__(self, "description", "WMDP-Chem benchmark adapter.")

    def benchmark_info(self) -> BenchmarkInfo:
        meta = _VARIANT_METADATA.get(self.variant, {})
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name=f"WMDP {self.variant.split('-', 1)[-1].title()}",
            short_description=f"WMDP {self.variant} multiple-choice benchmark",
            domain=meta.get("domain", "uncategorized"),
            benchmark_type=meta.get("benchmark_type", "capability"),
            family=meta.get("family", "wmdp"),
            primary_metric=meta.get("primary_metric", "accuracy"),
            higher_is_better=meta.get("higher_is_better", True),
            sample_preview_mode=meta.get("sample_preview_mode", "qa"),
            dashboard_tags=meta.get("dashboard_tags", []),
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        question = row.get("question", "")[:200]
        choices = row.get("choices", [])
        return {
            "id": row.get("id", ""),
            "question_preview": question,
            "choices_count": len(choices) if isinstance(choices, list) else 0,
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"scoring": "accuracy", "variant": self.variant}

    def _iter_rows(self) -> list[dict[str, Any]]:
        # Try local JSONL first, fall back to HuggingFace
        rows = _load_local_jsonl(self.dataset_path)
        if rows:
            return rows
        return _load_hf_rows(self.variant)

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get("split", "test"))

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        question = str(row.get("question", "")).strip()
        if not question:
            return None

        choices = row.get("choices", [])
        answer_index = row.get("answer", None)

        sample_id = str(row.get("id", "")).strip()
        if not sample_id:
            digest = hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]
            sample_id = f"wmdp-{row_index:06d}-{digest}"

        # Format MCQ prompt with labeled choices
        if isinstance(choices, list) and choices:
            choice_labels = "ABCD"
            choice_lines = []
            for i, c in enumerate(choices):
                label = choice_labels[i] if i < len(choice_labels) else str(i)
                choice_lines.append(f"{label}. {c}")
            formatted_input = f"{question}\n\n" + "\n".join(choice_lines)
            formatted_input += "\n\nAnswer with the letter of the correct choice."
        else:
            formatted_input = question

        return {
            "id": sample_id,
            "input": formatted_input,
            "metadata": {
                "choices": choices if isinstance(choices, list) else [],
                "answer": answer_index,
                "split": row_split,
                "variant": self.variant,
            },
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def _no_samples_error(self, split: str) -> str:
        return f"No WMDP samples loaded for split='{split}' (variant={self.variant})."
