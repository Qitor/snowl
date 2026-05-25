"""HumanEval benchmark adapter for Snowl evaluation.

Framework role:
- Maps HumanEval code generation data into Snowl Task/Sample contracts.
- Provides execution-based scoring via HumanEvalExecutionScorer.

Runtime/usage wiring:
- Registered as "humaneval" benchmark.
- Loaded by benchmark registry when user runs evaluations on code generation.

Change guardrails:
- Sample identity must be deterministic (based on task_id).
- Metadata contract must include task_id, entry_point, and test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path
from snowl.core import EnvSpec
from snowl.core.sample import Sample


class HumanEvalBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the HumanEval code generation benchmark.

    HumanEval evaluates agents on their ability to generate correct
    Python function implementations from docstring prompts.
    """

    name = "humaneval"
    description = "HumanEval — code generation benchmark"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load HumanEval data from local JSON or return empty list."""
        path = default_reference_path(
            __file__,
            "humaneval",
            "HumanEval.jsonl",
        )
        p = Path(path)
        if not p.exists():
            # Try alternate location
            alt_path = default_reference_path(
                __file__,
                "humaneval",
                "humaneval.jsonl",
            )
            p = Path(alt_path)
            if not p.exists():
                return []

        rows: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        """HumanEval has a single test split."""
        return "test"

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Filter by difficulty level if present."""
        diff_filter = filters.get("difficulty")
        if diff_filter is not None:
            row_diff = row.get("difficulty", row.get("level"))
            if str(row_diff).lower() != str(diff_filter).lower():
                return False
        return True

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        """Convert a HumanEval row to a Sample."""
        task_id = str(row.get("task_id", f"HumanEval/{row_index}"))
        prompt = row.get("prompt", "")
        test = row.get("test", "")
        entry_point = row.get("entry_point", "")
        canonical_solution = row.get("canonical_solution", "")

        if not prompt:
            return None

        sample = Sample(
            id=task_id.replace("/", "-").lower(),
            input=prompt,
            target=canonical_solution or None,
            metadata={
                "benchmark": "humaneval",
                "task_id": task_id,
                "entry_point": entry_point,
                "test": test,
                "canonical_solution": canonical_solution,
            },
        )
        return sample

    def _env_spec(self) -> EnvSpec:
        """Local environment — code execution handled by scorer."""
        return EnvSpec(env_type="local")

    def _no_samples_error(self, split: str) -> str:
        return (
            f"HumanEval: no samples found for split '{split}'. "
            f"Ensure HumanEval data (HumanEval.jsonl) is available locally."
        )
