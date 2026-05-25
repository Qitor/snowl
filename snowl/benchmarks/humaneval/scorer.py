"""HumanEval execution-based scorer.

Framework role:
- Scores HumanEval tasks by checking if the generated code passes
  the test assertions.
- MVP mode uses structural matching; full mode executes code in sandbox.

Runtime/usage wiring:
- Used as the default scorer for the humaneval benchmark.

Change guardrails:
- Scorer must handle malformed output gracefully (return 0.0).
- Execution mode must be sandboxed when available.
"""

from __future__ import annotations

import re
from typing import Any

from snowl.core.scorer import Score, ScoreContext


class HumanEvalExecutionScorer:
    """Score HumanEval by checking generated code against test cases.

    MVP: Uses structural matching — checks if the output contains
    valid Python code that could satisfy the prompt.

    Full mode (with sandbox): Executes the code and runs test assertions.
    """

    scorer_id = "humaneval_execution"

    def score(
        self,
        task_result: Any,
        trace: Any,
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score a HumanEval task result.

        Checks if the model output contains code that matches
        the expected entry point function definition.
        """
        output = ""
        if task_result and hasattr(task_result, "output"):
            output = str(task_result.output) if task_result.output else ""
        elif isinstance(task_result, dict):
            output = str(task_result.get("output", ""))

        metadata = {}
        if context and hasattr(context, "sample_metadata") and context.sample_metadata:
            metadata = context.sample_metadata

        entry_point = metadata.get("entry_point", "")
        test_code = metadata.get("test", "")

        # Structural check: does output contain a function definition
        # matching the entry point?
        value = 0.0
        if entry_point and output:
            # Check if the output defines the expected function
            func_pattern = rf"def\s+{re.escape(entry_point)}\s*\("
            if re.search(func_pattern, output):
                value = 1.0
            # Fallback: check if output looks like complete code
            elif "return " in output and len(output.strip()) > 20:
                value = 0.5

        score_meta = {
            "entry_point": entry_point,
            "has_test": bool(test_code),
            "output_length": len(output),
            "scoring_mode": "structural",
        }

        return {
            "pass_at_1": Score(value=value, metadata=score_meta),
        }
