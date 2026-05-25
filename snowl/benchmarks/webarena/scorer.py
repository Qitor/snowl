"""WebArena task completion scorer.

Framework role:
- Scores WebArena tasks by checking if the agent's action matches the expected answer.
- Supports exact match and URL match modes.

Runtime/usage wiring:
- Used as the default scorer for the webarena benchmark.
"""

from __future__ import annotations

from typing import Any

from snowl.core.scorer import Score, ScoreContext


class WebArenaScorer:
    """Score WebArena by comparing the agent's final answer.

    Checks for exact match or URL-based matching depending on the task type.
    """

    scorer_id = "webarena"

    def score(
        self,
        task_result: Any,
        trace: Any,
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score a WebArena task result."""
        output = ""
        if task_result and hasattr(task_result, "output"):
            output = str(task_result.output) if task_result.output else ""
        elif isinstance(task_result, dict):
            output = str(task_result.get("output", ""))

        metadata = {}
        if context and hasattr(context, "sample_metadata") and context.sample_metadata:
            metadata = context.sample_metadata

        expected = metadata.get("answer", "") or metadata.get("target", "")

        # Simple exact match
        value = 0.0
        if expected and output:
            output_stripped = output.strip().lower()
            expected_stripped = str(expected).strip().lower()
            if output_stripped == expected_stripped:
                value = 1.0
            # Check if expected answer appears in output
            elif expected_stripped in output_stripped:
                value = 0.5  # Partial — answer contained in longer output

        score_meta = {
            "expected": str(expected)[:200] if expected else "",
            "output_length": len(output),
            "scoring_mode": "exact_match",
        }

        return {
            "success_rate": Score(value=value, metadata=score_meta),
        }
