"""WebArena benchmark adapter for Snowl evaluation.

Framework role:
- Maps WebArena web interaction data into Snowl Task/Sample contracts.
- Provides GUI/terminal environment specification for browser-based evaluation.

Runtime/usage wiring:
- Registered as "webarena" benchmark.
- Loaded by benchmark registry for web interaction evaluations.

Change guardrails:
- Sample identity must be deterministic (based on task_id).
- Metadata contract must include task_id, intent, and URL.
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


class WebArenaBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the WebArena web interaction benchmark.

    WebArena evaluates agents on their ability to complete tasks
    by interacting with real web applications in a browser environment.
    """

    name = "webarena"
    description = "WebArena — web interaction benchmark"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load WebArena data from local JSON."""
        path = default_reference_path(
            __file__,
            "webarena",
            "webarena_test.json",
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
        """Filter by site type."""
        site_filter = filters.get("site")
        if site_filter is not None:
            row_site = row.get("site", "")
            if str(row_site).lower() != str(site_filter).lower():
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
        """Convert a WebArena row to a Sample."""
        task_id = str(row.get("task_id", f"webarena-{row_index}"))
        intent = row.get("intent", row.get("task", ""))
        url = row.get("start_url", row.get("url", ""))
        site = row.get("site", "")
        answer = row.get("answer", "")
        required_actions = row.get("required_actions", [])

        if not intent:
            return None

        # Build input from intent + URL context
        input_parts = [intent]
        if url:
            input_parts.append(f"\nStart URL: {url}")

        sample = Sample(
            id=f"webarena-{task_id}",
            input="\n".join(input_parts),
            target=answer or None,
            metadata={
                "benchmark": "webarena",
                "task_id": task_id,
                "site": site,
                "start_url": url,
                "required_actions": required_actions if isinstance(required_actions, list) else [],
            },
        )
        return sample

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with GUI/terminal environment and Docker sandbox."""
        return EnvSpec(
            env_type="terminal",
            provided_ops=(
                "process.run",
                "terminal.exec",
                "terminal.capture",
                "browser.navigate",
                "browser.click",
                "browser.type",
            ),
            sandbox_spec=SandboxSpec(
                provider="docker",
                image="webarena/eval:latest",
                metadata={"benchmark": "webarena"},
            ),
            config={"benchmark": "webarena"},
        )

    def _no_samples_error(self, split: str) -> str:
        return (
            f"WebArena: no samples found for split '{split}'. "
            f"Ensure WebArena data is available locally."
        )
