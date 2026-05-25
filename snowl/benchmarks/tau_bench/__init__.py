"""Tau-Bench benchmark adapter for Snowl evaluation.

Framework role:
- Maps Tau-Bench dataset rows into Snowl Task/Sample contracts.
- Supports airline and retail domains with per-domain filtering.
- Provides MCP server declarations for domain-specific tool APIs.

Runtime/usage wiring:
- Registered as "tau_bench_airline" and "tau_bench_retail" benchmarks.
- Loaded by benchmark registry when user runs ``snowl bench run tau_bench_airline``.

Change guardrails:
- Sample identity must be deterministic (based on test_id).
- Metadata contract must include domain, policy_rules, and expected_behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import build_benchmark_task, default_reference_path
from snowl.core import EnvSpec, Task
from snowl.core.mcp import MCPServerSpec
from snowl.core.sample import Sample
from snowl.errors import SnowlValidationError


class TauBenchBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the Tau-Bench policy compliance benchmark.

    Tau-Bench evaluates agents on their ability to follow domain-specific
    policies in multi-turn dialog scenarios. Two domains are supported:
    airline and retail.
    """

    name = "tau_bench"  # Overridden in __init__ per domain
    description = "Tau-Bench — policy compliance benchmark for tool-using agents"
    default_split = "test"

    def __init__(self, domain: str = "airline", **kwargs: Any) -> None:
        self.domain = domain
        self.name = f"tau_bench_{domain}"
        super().__init__(**kwargs)

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load Tau-Bench dataset rows from local JSON or HuggingFace."""
        rows = self._load_local()
        if rows:
            return rows
        return self._load_huggingface()

    def _load_local(self) -> list[dict[str, Any]]:
        """Try to load from local reference data."""
        path = default_reference_path(
            __file__,
            "tau_bench",
            f"tau_bench_{self.domain}",
            f"tau_bench_{self.domain}_test.json",
        )
        p = Path(path)
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []

    def _load_huggingface(self) -> list[dict[str, Any]]:
        """Try to load from HuggingFace datasets."""
        try:
            from datasets import load_dataset
            ds = load_dataset(
                "tau-bench/tau_bench",
                self.domain,
                split="test",
                trust_remote_code=True,
            )
            rows = []
            for item in ds:
                rows.append(dict(item))
            return rows
        except Exception:
            return []

    def _row_split(self, row: dict[str, Any]) -> str:
        """Tau-Bench uses a single test split per domain."""
        return "test"

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Filter by difficulty if specified."""
        diff = filters.get("difficulty")
        if diff is None:
            return True
        row_diff = row.get("difficulty", row.get("level"))
        return str(row_diff) == str(diff)

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        """Convert a Tau-Bench row to a Sample."""
        test_id = str(row.get("id", row.get("test_id", f"tau-{self.domain}-{row_index}")))
        initial_prompt = row.get("initial_prompt", row.get("prompt", row.get("user_message", "")))
        expected_behavior = row.get("expected_behavior", row.get("expected", ""))
        policy_rules = row.get("policy_rules", row.get("rules", []))
        difficulty = row.get("difficulty", row.get("level", "medium"))

        # Build the input: the initial user message
        if isinstance(initial_prompt, list):
            input_content = initial_prompt
        else:
            input_content = str(initial_prompt)

        sample = Sample(
            id=f"tau-{self.domain}-{test_id}",
            input=input_content,
            target=str(expected_behavior) if expected_behavior else None,
            metadata={
                "benchmark": "tau_bench",
                "domain": self.domain,
                "test_id": test_id,
                "expected_behavior": expected_behavior,
                "policy_rules": policy_rules if isinstance(policy_rules, list) else [],
                "difficulty": difficulty,
            },
        )
        return sample.to_dict()

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with MCP server for the domain's tool API."""
        mcp_server = MCPServerSpec(
            name=f"{self.domain}_api",
            transport="stdio",
            command="python",
            args=(f"-m", f"tau_bench_{self.domain}_server",),
            metadata={"domain": self.domain},
        )
        return EnvSpec(
            env_type="dialog",
            provided_ops=("tool.call",),
            mcp_servers=(mcp_server,),
            config={"benchmark": "tau_bench", "domain": self.domain},
        )

    def _no_samples_error(self, split: str) -> str:
        return (
            f"Tau-Bench ({self.domain}): no samples found for split '{split}'. "
            f"Ensure Tau-Bench dataset is available locally or install 'datasets' package."
        )
