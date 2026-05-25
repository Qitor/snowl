"""GAIA benchmark scorer — answer matching with normalization."""

from __future__ import annotations

import re
from typing import Any

from snowl.core.scorer import Score, ScoreContext


class GAIAScorer:
    """Score GAIA answers using exact + normalized matching.

    Normalization includes:
    - Case folding
    - Whitespace collapsing
    - Trailing punctuation removal
    - Common unit normalization (%, dollars, degrees)
    """

    scorer_id: str = "gaia"

    def score(
        self,
        task_result: Any,
        tool_results: Any,
        context: ScoreContext,
    ) -> dict[str, Score]:
        expected = ""
        if context.sample_metadata:
            expected = str(context.sample_metadata.get("final_answer") or "").strip()

        output = ""
        if hasattr(task_result, "output"):
            output = str(task_result.output or "")
        elif isinstance(task_result, dict):
            output = str(task_result.get("output") or "")

        # Try to extract answer from output
        extracted = self._extract_answer(output)
        if extracted is None:
            extracted = output.strip()

        expected_norm = self._normalize(expected)
        extracted_norm = self._normalize(extracted)

        if expected_norm and extracted_norm == expected_norm:
            value = 1.0
        elif expected_norm and expected_norm in extracted_norm:
            value = 0.5  # Partial match — answer contained in output
        else:
            value = 0.0

        return {
            "accuracy": Score(value=value),
        }

    @staticmethod
    def _extract_answer(text: str) -> str | None:
        """Try to extract a final answer from model output."""
        m = re.search(r"(?:the answer is|answer:)\s*(.+?)(?:\.|$)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"ANSWER:\s*(.+?)(?:\.|$)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize answer for comparison."""
        t = text.strip().lower()
        t = re.sub(r"[.,;:!?\)]+$", "", t)
        t = t.replace("percent", "%").replace(" per cent", "%")
        t = t.replace("dollars", "$").replace("dollar", "$")
        t = t.replace("degrees", "\u00b0").replace("degree", "\u00b0")
        # Collapse whitespace after substitutions
        t = re.sub(r"\s+", " ", t).strip()
        # Remove space between number and symbol
        t = re.sub(r"(\d)\s+([%$\u00b0])", r"\1\2", t)
        t = re.sub(r"([$€£])\s+", r"\1", t)
        t = re.sub(r"(\d),(\d)", r"\1\2", t)
        return t
