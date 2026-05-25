"""CyberGym benchmark adapter for Snowl evaluation.

Framework role:
- Maps CyberGym security capability data into Snowl Task/Sample contracts.
- Provides terminal/Docker environment for cybersecurity CTF evaluation.

Runtime/usage wiring:
- Registered as "cybergym" benchmark.
- Loaded by benchmark registry for cybersecurity capability evaluations.

Change guardrails:
- Sample identity must be deterministic (based on challenge_id).
- Metadata contract must include challenge_id, category, and difficulty.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import default_reference_path
from snowl.core import EnvSpec
from snowl.core.env import SandboxSpec
from snowl.core.sample import Sample


class CyberGymBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the CyberGym security capability benchmark.

    CyberGym evaluates agents on cybersecurity capability tasks
    across multiple categories including penetration testing,
    vulnerability analysis, and security tool usage.
    """

    name = "cybergym"
    description = "CyberGym — security capability benchmark"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load CyberGym data from local JSON."""
        path = default_reference_path(
            __file__,
            "cybergym",
            "cybergym_challenges.json",
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
        """Return split based on challenge category."""
        category = row.get("category", row.get("type", "misc"))
        return str(category)

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Filter by category and difficulty."""
        cat_filter = filters.get("category")
        if cat_filter is not None:
            row_cat = row.get("category", row.get("type"))
            if str(row_cat).lower() != str(cat_filter).lower():
                return False

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
        """Convert a CyberGym row to a Sample."""
        challenge_id = str(row.get("id", row.get("challenge_id", f"cybergym-{row_index}")))
        description = row.get("description", row.get("prompt", ""))
        flag = row.get("flag", row.get("answer", ""))
        category = row.get("category", row.get("type", "misc"))
        difficulty = row.get("difficulty", row.get("level", "medium"))
        hints = row.get("hints", [])

        if not description:
            return None

        input_content = str(description) if not isinstance(description, list) else description

        sample = Sample(
            id=f"cybergym-{challenge_id}",
            input=input_content,
            target=str(flag) if flag else None,
            metadata={
                "benchmark": "cybergym",
                "challenge_id": challenge_id,
                "category": category,
                "difficulty": difficulty,
                "flag": flag,
                "hints": hints if isinstance(hints, list) else [],
            },
        )
        return sample.to_dict()

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with terminal environment and Docker sandbox."""
        return EnvSpec(
            env_type="terminal",
            provided_ops=("process.run", "terminal.exec", "terminal.capture"),
            sandbox_spec=SandboxSpec(
                provider="docker",
                image="cybergym/challenge-base:latest",
                metadata={"benchmark": "cybergym"},
            ),
            config={"benchmark": "cybergym"},
        )

    def _no_samples_error(self, split: str) -> str:
        return (
            f"CyberGym: no samples found for split '{split}'. "
            f"Ensure CyberGym challenge data is available locally."
        )
