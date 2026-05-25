"""CyBench benchmark adapter for Snowl evaluation.

Framework role:
- Maps CyBench CTF challenge data into Snowl Task/Sample contracts.
- Supports multiple challenge categories (web, crypto, pwn, reverse, misc).
- Provides Docker sandbox environment specification.

Runtime/usage wiring:
- Registered as "cybench" benchmark.
- Loaded by benchmark registry when user runs ``snowl bench run cybench``.

Change guardrails:
- Sample identity must be deterministic (based on challenge_id).
- Metadata contract must include challenge_id, category, difficulty, and flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import build_benchmark_task, default_reference_path
from snowl.core import EnvSpec, Task
from snowl.core.env import SandboxSpec
from snowl.core.sample import Sample
from snowl.errors import SnowlValidationError


class CyBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the CyBench cybersecurity CTF benchmark.

    CyBench evaluates agents on their ability to solve CTF-style
    cybersecurity challenges across multiple categories.
    """

    name = "cybench"
    description = "CyBench — cybersecurity CTF benchmark"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load CyBench challenge data from local directory or JSON."""
        rows = self._load_local()
        if rows:
            return rows
        return self._load_json()

    def _load_local(self) -> list[dict[str, Any]]:
        """Try to load from local reference data directory."""
        base_path = default_reference_path(
            __file__,
            "cybench",
            "challenges",
            "",
        )
        base = Path(base_path)
        if not base.exists() or not base.is_dir():
            return []

        rows: list[dict[str, Any]] = []
        # Scan challenge subdirectories for challenge.json or challenge.yml
        for challenge_dir in sorted(base.iterdir()):
            if not challenge_dir.is_dir():
                continue
            challenge_file = challenge_dir / "challenge.json"
            if challenge_file.exists():
                try:
                    with challenge_file.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["_source_dir"] = str(challenge_dir)
                    rows.append(data)
                except Exception:
                    continue
        return rows

    def _load_json(self) -> list[dict[str, Any]]:
        """Try to load from a single JSON file."""
        path = default_reference_path(
            __file__,
            "cybench",
            "cybench_challenges.json",
        )
        p = Path(path)
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []

    def _row_split(self, row: dict[str, Any]) -> str:
        """Determine split from challenge category."""
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
        """Convert a CyBench row to a Sample."""
        challenge_id = str(row.get("id", row.get("challenge_id", f"cyber-{row_index}")))
        description = row.get("description", row.get("prompt", ""))
        flag = row.get("flag", row.get("answer", ""))
        category = row.get("category", row.get("type", "misc"))
        difficulty = row.get("difficulty", row.get("level", "medium"))
        hints = row.get("hints", [])
        source_dir = row.get("_source_dir", "")

        if isinstance(description, list):
            input_content = description
        else:
            input_content = str(description)

        sample = Sample(
            id=f"cyber-{challenge_id}",
            input=input_content,
            target=str(flag) if flag else None,
            metadata={
                "benchmark": "cybench",
                "challenge_id": challenge_id,
                "category": category,
                "difficulty": difficulty,
                "flag": flag,
                "hints": hints if isinstance(hints, list) else [],
                "source_dir": source_dir,
            },
        )
        return sample

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with terminal environment and Docker sandbox."""
        return EnvSpec(
            env_type="terminal",
            provided_ops=("process.run", "terminal.exec", "terminal.capture"),
            sandbox_spec=SandboxSpec(
                provider="docker",
                image="cybench/challenge-base:latest",
                metadata={"benchmark": "cybench"},
            ),
            config={"benchmark": "cybench"},
        )

    def _no_samples_error(self, split: str) -> str:
        return (
            f"CyBench: no samples found for split '{split}'. "
            f"Ensure CyBench challenge data is available locally."
        )
