"""Adapter layer that maps `strongreject` source datasets into Snowl task/sample contracts.

Framework role:
- Owns benchmark-specific split/filter/sample-id logic and metadata extraction.
- Keeps shared runtime generic by normalizing benchmark rows into standard task inputs.

Runtime/usage wiring:
- Loaded by benchmark registry/bench orchestration and executed through the shared eval pipeline.
- Key top-level symbols in this file: `_default_dataset_path`, `StrongRejectBenchmarkAdapter`.

Change guardrails:
- Preserve deterministic sample identity and metadata contract; scorer/runtime layers depend on it.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path
from snowl.core import EnvSpec
from snowl.errors import SnowlValidationError

# Pinned GitHub commit for reproducibility (same as inspect_evals reference).
_STRONGREJECT_CSV_URL = (
    "https://raw.githubusercontent.com/alexandrasouly/strongreject/"
    "3432b2d696b428f242bd507df96d80f686571d5e/"
    "strongreject_dataset/strongreject_dataset.csv"
)


def _default_dataset_path() -> str:
    return default_reference_path(
        __file__,
        "strongreject",
        "strongreject_dataset",
        "strongreject_small_dataset.csv",
    )


def _load_rows_from_csv(path: str) -> list[dict[str, Any]]:
    """Load rows from a local CSV file."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def _load_rows_from_url() -> list[dict[str, Any]]:
    """Download StrongReject CSV from pinned GitHub URL and parse rows."""
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise SnowlValidationError(
            "Missing optional dependency 'requests'. "
            "Install Snowl with the 'safety_assets' extra to use remote benchmark assets."
        ) from exc

    from snowl.benchmarks.assets import benchmark_cache_root

    cache_dir = benchmark_cache_root() / "direct_url"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "strongreject_dataset.csv"

    if not cache_file.exists():
        resp = requests.get(_STRONGREJECT_CSV_URL, timeout=60)
        resp.raise_for_status()
        cache_file.write_bytes(resp.content)

    rows: list[dict[str, Any]] = []
    with cache_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


@dataclass(frozen=True)
class StrongRejectBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = _default_dataset_path()
    name: str = "strongreject"
    description: str = "StrongReject benchmark adapter."
    split_field: str = "split"
    default_split: str = "test"
    prompt_field: str = "forbidden_prompt"
    id_field: str = "id"

    def _iter_rows(self) -> list[dict[str, Any]]:
        # Try local file first, fall back to remote download
        rows = _load_rows_from_csv(self.dataset_path)
        if rows:
            return rows
        return _load_rows_from_url()

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        _ = row_index
        return str(row.get(self.split_field) or self.default_split)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        _ = selected_count
        prompt = str(row.get(self.prompt_field) or "").strip()
        if not prompt:
            return None

        sample_id = str(row.get(self.id_field) or "").strip()
        if not sample_id:
            digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
            sample_id = f"sr-{row_index:06d}-{digest}"

        return {
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

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "input_preview": str(row.get("forbidden_prompt", ""))[:200],
            "category": row.get("category", ""),
            "source": row.get("source", ""),
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"scoring": "strongreject"}

    def _task_metadata(self, *, split: str, selected_count: int) -> dict[str, Any]:
        _ = selected_count
        return {
            "benchmark": self.name,
            "split": split,
            "dataset_path": str(self.dataset_path),
            "scoring": "strongreject",
        }

    def _no_samples_error(self, split: str) -> str:
        return f"No StrongReject samples loaded for split='{split}'."
