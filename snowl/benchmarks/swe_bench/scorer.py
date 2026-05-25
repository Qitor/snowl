"""SWE-Bench patch scorer.

Framework role:
- Scores SWE-Bench tasks by evaluating generated patches.
- MVP mode checks patch structural validity.
- Full mode applies patch in container and runs test suite.

Runtime/usage wiring:
- Used as the default scorer for SWE-Bench benchmarks.

Change guardrails:
- Scorer must handle malformed output gracefully.
- Full evaluation requires Docker environment.
"""

from __future__ import annotations

import re
from typing import Any

from snowl.core.scorer import Score, ScoreContext


class SWEBenchPatchScorer:
    """Score SWE-Bench by evaluating the generated patch.

    MVP: Checks structural validity — whether the output looks like
    a valid diff/patch that could apply to the target repo.

    Full mode (with Docker): Applies the patch and runs the test suite.
    """

    scorer_id = "swe_bench_patch"

    # Minimal unified diff header pattern
    _DIFF_HEADER = re.compile(r"^diff --git", re.MULTILINE)
    _HUNK_HEADER = re.compile(r"^@@ -\d+,?\d* \+\d+,?\d* @@", re.MULTILINE)

    def score(
        self,
        task_result: Any,
        trace: Any,
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score a SWE-Bench task result.

        Checks if the model output contains a structurally valid patch.
        """
        output = ""
        if task_result and hasattr(task_result, "output"):
            output = str(task_result.output) if task_result.output else ""
        elif isinstance(task_result, dict):
            output = str(task_result.get("output", ""))

        # Check for patch content
        has_diff_header = bool(self._DIFF_HEADER.search(output))
        has_hunk_header = bool(self._HUNK_HEADER.search(output))

        # Also check for simple code blocks that might be patches
        has_code_block = bool(re.search(r"```(?:diff|patch)?\n", output))

        # Determine score
        if has_diff_header and has_hunk_header:
            value = 1.0  # Complete unified diff
            quality = "complete_diff"
        elif has_diff_header:
            value = 0.7  # Partial diff (has header but missing hunk markers)
            quality = "partial_diff"
        elif has_code_block and ("-" in output and "+" in output):
            value = 0.5  # Code changes in a block (might be a patch)
            quality = "code_changes"
        else:
            value = 0.0
            quality = "no_patch"

        score_meta = {
            "has_diff_header": has_diff_header,
            "has_hunk_header": has_hunk_header,
            "has_code_block": has_code_block,
            "output_length": len(output),
            "scoring_mode": "structural",
            "quality": quality,
        }

        return {
            "resolved": Score(value=value, metadata=score_meta),
        }
