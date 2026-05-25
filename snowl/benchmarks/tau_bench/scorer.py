"""Tau-Bench policy compliance scorer.

Framework role:
- Evaluates whether an agent's actions comply with domain-specific policy rules.
- Reads expected behavior and policy rules from sample metadata.

Runtime/usage wiring:
- Used as a scorer in Tau-Bench evaluation runs.

Change guardrails:
- Scoring logic must be deterministic for the same input.
"""

from __future__ import annotations

import re
from typing import Any

from snowl.core.scorer import Score, ScoreContext


class TauBenchPolicyScorer:
    """Score agent compliance with domain-specific policy rules.

    Checks whether the agent's final answer matches the expected behavior
    described in sample metadata.
    """

    scorer_id: str = "tau_bench_policy"
    metric_name: str = "policy_compliance"

    def score(
        self,
        task_result: Any,
        trace: dict[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Evaluate policy compliance.

        Args:
            task_result: The TaskResult from the agent's run.
            trace: Execution trace with actions and observations.
            context: ScoreContext with sample metadata.

        Returns:
            Dict with 'policy_compliance' and 'pass_rate' scores.
        """
        sample_meta = context.sample_metadata or {}
        expected = sample_meta.get("expected_behavior", "")
        if not expected:
            return {
                "policy_compliance": Score(value=0.0, explanation="No expected behavior defined"),
                "pass_rate": Score(value=0.0, explanation="No expected behavior defined"),
            }

        # Extract the agent's final answer
        agent_output = self._extract_final_answer(task_result, trace)

        # Simple string matching / containment check
        compliance = self._check_compliance(agent_output, expected)

        return {
            "policy_compliance": Score(
                value=1.0 if compliance else 0.0,
                explanation="Agent complied with policy" if compliance else "Agent violated policy",
            ),
            "pass_rate": Score(
                value=1.0 if compliance else 0.0,
                explanation="Pass" if compliance else "Fail",
            ),
        }

    def _extract_final_answer(self, task_result: Any, trace: dict[str, Any]) -> str:
        """Extract the agent's final answer from the task result or trace."""
        # Try task_result.answer first
        answer = getattr(task_result, "answer", None)
        if answer:
            return str(answer)

        # Try last message in trace
        messages = trace.get("messages", [])
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))

        # Try output field
        output = getattr(task_result, "output", None)
        if output:
            return str(output)

        return ""

    def _check_compliance(self, agent_output: str, expected: str) -> bool:
        """Check if agent output complies with expected behavior.

        Uses flexible matching: either exact substring match or
        key phrase extraction.
        """
        if not agent_output or not expected:
            return False

        output_lower = agent_output.lower().strip()
        expected_lower = expected.lower().strip()

        # Direct containment check
        if expected_lower in output_lower:
            return True

        # Extract key phrases from expected behavior
        # Split on common delimiters and check each phrase
        phrases = re.split(r"[;,.\n]", expected_lower)
        phrases = [p.strip() for p in phrases if len(p.strip()) > 5]

        if not phrases:
            return expected_lower in output_lower

        # Check if majority of key phrases appear in output
        matches = sum(1 for p in phrases if p in output_lower)
        return matches >= len(phrases) * 0.5
