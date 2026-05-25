"""SWE-Bench benchmark adapter for Snowl evaluation.

Framework role:
- Maps SWE-Bench software engineering data into Snowl Task/Sample contracts.
- Supports subset selection (lite, verified).
- Provides Docker sandbox environment for patch evaluation.

Runtime/usage wiring:
- Registered as "swe_bench_lite" and "swe_bench_verified" benchmarks.
- Loaded by benchmark registry for software engineering evaluations.

Change guardrails:
- Sample identity must be deterministic (based on instance_id).
- Metadata contract must include instance_id, repo, base_commit.
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


class SWEBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the SWE-Bench software engineering benchmark.

    SWE-Bench evaluates agents on their ability to resolve GitHub
    issues by generating patches against real repository snapshots.

    Subsets:
    - "lite": 300 instances, commonly used for quick evaluation.
    - "verified": 500 instances, human-verified for quality.
    """

    name = "swe_bench"
    description = "SWE-Bench — software engineering benchmark"
    default_split = "test"

    def __init__(self, subset: str = "lite", **kwargs: Any) -> None:
        self.subset = subset
        self.name = f"swe_bench_{subset}"
        self.description = f"SWE-Bench {subset} — software engineering benchmark"
        super().__init__(**kwargs)

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load SWE-Bench data from local JSON."""
        filename = f"swe_bench_{self.subset}.json"
        path = default_reference_path(
            __file__,
            "swe_bench",
            filename,
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
        """Filter by repo name."""
        repo_filter = filters.get("repo")
        if repo_filter is not None:
            row_repo = row.get("repo", "")
            if str(row_repo).lower() != str(repo_filter).lower():
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
        """Convert a SWE-Bench row to a Sample."""
        instance_id = str(row.get("instance_id", f"swe-{row_index}"))
        problem_statement = row.get("problem_statement", "")
        repo = row.get("repo", "")
        base_commit = row.get("base_commit", "")
        patch = row.get("patch", "")
        test_patch = row.get("test_patch", "")
        version = row.get("version", "")
        hints_text = row.get("hints_text", "")

        if not problem_statement:
            return None

        # Build input: the problem statement (GitHub issue text)
        input_parts = [problem_statement]
        if hints_text:
            input_parts.append(f"\nHints:\n{hints_text}")

        sample = Sample(
            id=instance_id.replace("/", "__").replace(".", "-"),
            input="\n".join(input_parts),
            target=patch or None,
            metadata={
                "benchmark": "swe_bench",
                "subset": self.subset,
                "instance_id": instance_id,
                "repo": repo,
                "base_commit": base_commit,
                "patch": patch,
                "test_patch": test_patch,
                "version": version,
            },
        )
        return sample

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with terminal environment and Docker sandbox."""
        return EnvSpec(
            env_type="terminal",
            provided_ops=(
                "process.run",
                "terminal.exec",
                "file.read",
                "file.write",
            ),
            sandbox_spec=SandboxSpec(
                provider="docker",
                image=f"swe-bench/{self.subset}:latest",
                metadata={"benchmark": "swe_bench", "subset": self.subset},
            ),
            config={"benchmark": "swe_bench", "subset": self.subset},
        )

    def _no_samples_error(self, split: str) -> str:
        return (
            f"SWE-Bench ({self.subset}): no samples found for split '{split}'. "
            f"Ensure SWE-Bench data is available locally."
        )
