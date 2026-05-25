"""Benchmark adapter template — copy and customize for your benchmark.

Steps:
1. Copy this file to snowl/benchmarks/<your_benchmark>/__init__.py
2. Implement _iter_rows(), _row_split(), _row_to_sample()
3. Add a scorer.py if needed (see scorer template below)
4. Register in snowl/benchmarks/registry.py
5. Run: snowl bench check <your_benchmark>

Replace all placeholder values marked with {{...}}.
"""

from __future__ import annotations

from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.core import EnvSpec
from snowl.core.sample import Sample


class {{BenchmarkName}}Adapter(BaseBenchmarkAdapter[dict[str, Any]]):
    """Adapter for the {{benchmark_name}} benchmark."""

    name = "{{benchmark_name}}"
    description = "{{benchmark_name}} — {{one_line_description}}"
    default_split = "test"

    def _iter_rows(self) -> list[dict[str, Any]]:
        """Load benchmark data from local files or external sources.

        Return a list of dicts, each representing one sample.
        """
        # TODO: Load from JSON/JSONL/CSV or HuggingFace datasets
        return []

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        """Return the split name for this row (e.g. 'train', 'test')."""
        return str(row.get("split", "test"))

    def _row_to_sample(
        self,
        row: dict[str, Any],
        *,
        row_index: int,
        row_split: str,
        selected_count: int,
    ) -> dict[str, Any] | None:
        """Convert a raw data row to a Sample dict.

        Required fields in the returned dict:
        - id: unique sample identifier
        - input: the prompt/question/task description
        - metadata: dict with at least 'benchmark' key

        Optional fields:
        - target: expected answer (for scorer matching)
        """
        input_text = row.get("input", row.get("prompt", ""))
        if not input_text:
            return None

        sample = Sample(
            id=f"{{benchmark_name}}-{row_index}",
            input=str(input_text),
            target=row.get("target", row.get("answer")),
            metadata={
                "benchmark": "{{benchmark_name}}",
                # Add domain-specific metadata here
            },
        )
        return sample.to_dict()

    def _env_spec(self) -> EnvSpec:
        """Environment specification for this benchmark."""
        return EnvSpec(env_type="local")


# --- Scorer template (save as scorer.py) ---
#
# from snowl.core.scorer import Score, ScoreContext
#
# class {{BenchmarkName}}Scorer:
#     scorer_id = "{{benchmark_name}}"
#
#     def score(self, task_result, trace, context) -> dict[str, Score]:
#         output = ""
#         if task_result and hasattr(task_result, "output"):
#             output = str(task_result.output) if task_result.output else ""
#         expected = context.sample_metadata.get("target", "")
#         value = 1.0 if output.strip() == expected.strip() else 0.0
#         return {"accuracy": Score(value=value)}
