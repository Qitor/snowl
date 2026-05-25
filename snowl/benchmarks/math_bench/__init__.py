"""MATH benchmark adapter for Snowl evaluation.

Framework role:
- Maps MATH mathematical reasoning data into Snowl Task/Sample contracts.
- Provides answer extraction and normalization scoring.

Runtime/usage wiring:
- Registered as "math" benchmark.
- Loaded by benchmark registry for mathematical reasoning evaluations.

Change guardrails:
- Sample identity must be deterministic (based on problem index).
- Metadata contract must include answer, subject, level.
- Directory is named math_bench to avoid shadowing Python's math module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path
from snowl.core import EnvSpec
from snowl.core.sample import Sample


class MATHBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the MATH mathematical reasoning benchmark.

    MATH evaluates agents on their ability to solve mathematics
    problems across multiple subjects and difficulty levels.
    """

    name = "math"
    description = "MATH — mathematical reasoning benchmark"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load MATH data from local JSON/JSONL or return empty list."""
        # Try JSONL first
        path = default_reference_path(
            __file__,
            "math_bench",
            "math_test.jsonl",
        )
        p = Path(path)
        if p.exists():
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

        # Try JSON
        path = default_reference_path(
            __file__,
            "math_bench",
            "math_test.json",
        )
        p = Path(path)
        if not p.exists():
            return []

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        """Return split from row data or default."""
        return str(row.get("split", "test"))

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Filter by subject and level."""
        subject_filter = filters.get("subject")
        if subject_filter is not None:
            row_subject = row.get("subject", row.get("type", ""))
            if str(row_subject).lower() != str(subject_filter).lower():
                return False

        level_filter = filters.get("level")
        if level_filter is not None:
            row_level = row.get("level", "")
            if str(row_level) != str(level_filter):
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
        """Convert a MATH row to a Sample."""
        problem = row.get("problem", "")
        solution = row.get("solution", "")
        answer = row.get("answer", "")
        subject = row.get("subject", row.get("type", ""))
        level = row.get("level", "")

        if not problem:
            return None

        # Extract answer from solution if not directly provided
        if not answer and solution:
            extracted = _extract_boxed_answer(solution)
            if extracted is not None:
                answer = extracted

        sample = Sample(
            id=f"math-{row_index}",
            input=problem,
            target=answer or None,
            metadata={
                "benchmark": "math",
                "answer": answer,
                "subject": subject,
                "level": level,
                "has_solution": bool(solution),
            },
        )
        return sample

    def _env_spec(self) -> EnvSpec:
        """Local environment — no execution needed for answer matching."""
        return EnvSpec(env_type="local")

    def _no_samples_error(self, split: str) -> str:
        return (
            f"MATH: no samples found for split '{split}'. "
            f"Ensure MATH data is available locally."
        )


def _extract_boxed_answer(text: str) -> str | None:
    """Extract the answer from \\boxed{...} in the solution text."""
    import re
    match = re.search(r"\\boxed\{([^}]+)\}", text)
    if match:
        return match.group(1).strip()
    return None
