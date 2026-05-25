"""GAIA general AI assistant benchmark adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.utils import read_json_array, stable_benchmark_id
from snowl.core import EnvSpec
from snowl.core.sample import Sample
from snowl.errors import SnowlValidationError


@dataclass(frozen=True)
class GAIABenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """GAIA benchmark adapter — general AI assistant evaluation.

    GAIA tests agents on real-world tasks requiring reasoning, multi-modal
    understanding, and tool use. Levels L1/L2/L3 indicate difficulty.

    Row format:
        task_id, question, level, final_answer, file_name, file_path
    """

    dataset_path: str = ""
    rows: list[dict[str, Any]] | None = None
    name: str = "gaia"
    description: str = "GAIA general AI assistant benchmark — real-world reasoning with tool use"
    default_split: str = "test"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            display_name="GAIA",
            short_description="General AI assistant benchmark",
            domain="agentic_capability",
            benchmark_type="capability",
            family="gaia",
            primary_metric="gaia_accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["reasoning", "tool_use", "multi_modal"],
        )

    def _iter_rows(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return [dict(row) for row in self.rows]
        if not self.dataset_path:
            raise SnowlValidationError("GAIA benchmark requires rows=... or dataset_path=....")
        data = read_json_array(
            self.dataset_path,
            not_found_message="GAIA dataset not found",
            invalid_message="GAIA dataset must be a JSON array",
        )
        return [dict(row) for row in data if isinstance(row, dict)]

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        level = row.get("level", "")
        if level:
            return f"L{int(level)}" if isinstance(level, (int, float)) else str(level)
        return self.default_split

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> Sample | dict[str, Any] | None:
        _ = selected_count
        question = str(row.get("question") or "").strip()
        if not question:
            return None

        task_id = str(row.get("task_id") or "").strip() or stable_benchmark_id("gaia", row_index, question)
        final_answer = str(row.get("final_answer") or "").strip()
        level = row.get("level", "")
        level_str = f"L{int(level)}" if isinstance(level, (int, float)) else str(level)
        file_name = str(row.get("file_name") or "").strip()
        file_path = str(row.get("file_path") or "").strip()

        # Build input prompt
        input_text = question
        if file_name:
            input_text += f"\n\nAttached file: {file_name}"

        return Sample(
            id=f"gaia-{task_id}" if not task_id.startswith("gaia-") else task_id,
            input=input_text,
            target=final_answer if final_answer else None,
            metadata={
                "benchmark": "gaia",
                "task_id": task_id,
                "level": level_str,
                "file_name": file_name or None,
                "file_path": file_path or None,
                "final_answer": final_answer or None,
            },
        )

    def _env_spec(self) -> EnvSpec:
        """EnvSpec with terminal + browser for file operations."""
        return EnvSpec(
            env_type="terminal",
            provided_ops=("process.run", "terminal.exec", "terminal.capture"),
        )

    def _matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        if "level" in filters:
            row_level = row.get("level", "")
            row_level_str = f"L{int(row_level)}" if isinstance(row_level, (int, float)) else str(row_level)
            filter_level = str(filters["level"])
            if not filter_level.startswith("L"):
                filter_level = f"L{filter_level}"
            if row_level_str != filter_level:
                return False
            # Remove level from filters so base class doesn't re-compare
            filters = {k: v for k, v in filters.items() if k != "level"}
        return super()._matches_filters(row, filters)
