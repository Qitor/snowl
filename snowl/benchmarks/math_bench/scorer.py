"""MATH answer extraction and normalization scorer.

Framework role:
- Scores MATH tasks by extracting the final answer from model output
  and comparing it to the expected answer.
- Handles LaTeX boxed format, natural language answers, and bare numbers.

Runtime/usage wiring:
- Used as the default scorer for the MATH benchmark.

Change guardrails:
- Answer normalization must be conservative — false negatives are
  preferable to false positives.
- LaTeX equivalence is approximate (simple normalization only).
"""

from __future__ import annotations

import re
from typing import Any

from snowl.core.scorer import Score, ScoreContext


class MATHAnswerScorer:
    """Score MATH by extracting and comparing the final answer.

    Supports:
    - ``\\boxed{...}`` LaTeX format
    - "The answer is: ..." natural language
    - Bare numeric final line
    - Simple fraction/decimal normalization
    """

    scorer_id = "math_answer"

    def score(
        self,
        task_result: Any,
        trace: Any,
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score a MATH task result by comparing extracted answers."""
        output = ""
        if task_result and hasattr(task_result, "output"):
            output = str(task_result.output) if task_result.output else ""
        elif isinstance(task_result, dict):
            output = str(task_result.get("output", ""))

        metadata = {}
        if context and hasattr(context, "sample_metadata") and context.sample_metadata:
            metadata = context.sample_metadata

        expected = metadata.get("answer", "")

        # Extract answer from model output
        extracted = self._extract_answer(output)

        # Compare
        if extracted is not None and expected:
            normalized_extracted = self._normalize_answer(extracted)
            normalized_expected = self._normalize_answer(expected)
            value = 1.0 if normalized_extracted == normalized_expected else 0.0
        else:
            value = 0.0

        score_meta = {
            "expected": expected,
            "extracted": extracted,
            "scoring_mode": "answer_extraction",
        }

        return {
            "accuracy": Score(value=value, metadata=score_meta),
        }

    def _extract_answer(self, text: str) -> str | None:
        """Extract the final answer from model output.

        Tries in order:
        1. \\boxed{...} LaTeX format
        2. "The answer is: ..." or "The answer is ..."
        3. Last line that looks like a number or expression
        """
        if not text or not text.strip():
            return None

        # Try \boxed{...}
        boxed_match = re.search(r"\\boxed\{([^}]+)\}", text)
        if boxed_match:
            return boxed_match.group(1).strip()

        # Try "The answer is: ..." or "The answer is ..."
        answer_match = re.search(
            r"(?:the\s+answer\s+is)[:\s]+(.+?)(?:\.|$)",
            text,
            re.IGNORECASE,
        )
        if answer_match:
            return answer_match.group(1).strip()

        # Try last line that looks like a number
        lines = text.strip().split("\n")
        for line in reversed(lines):
            stripped = line.strip()
            if not stripped:
                continue
            # Check if it looks like a numeric answer
            if re.match(r"^-?[\d.,/]+$", stripped):
                return stripped
            # Check for simple expressions
            if re.match(r"^-?[\d.,/\s+\-()]+$", stripped) and len(stripped) < 30:
                return stripped

        return None

    def _normalize_answer(self, answer: str) -> str:
        """Normalize an answer for comparison.

        Handles:
        - Whitespace normalization
        - Fraction to decimal (simple cases)
        - Negative sign normalization
        - Trailing zeros in decimals
        """
        if not answer:
            return ""

        normalized = answer.strip()
        # Remove surrounding parentheses
        normalized = normalized.strip("()")

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Try to evaluate simple fractions
        fraction_match = re.match(r"^(-?\d+)\s*/\s*(-?\d+)$", normalized)
        if fraction_match:
            num, den = int(fraction_match.group(1)), int(fraction_match.group(2))
            if den != 0:
                result = num / den
                # Use decimal if clean, otherwise fraction
                if result == int(result):
                    return str(int(result))
                return str(result)

        # Try numeric evaluation for simple expressions
        try:
            # Only evaluate simple numeric expressions
            if re.match(r"^-?[\d.+\-*/()\s]+$", normalized):
                result = eval(normalized)  # noqa: S307
                if isinstance(result, float):
                    if result == int(result):
                        return str(int(result))
                    return str(result)
                return str(result)
        except Exception:
            pass

        return normalized.lower()
