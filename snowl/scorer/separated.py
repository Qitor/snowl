"""Separated-mode scorers that run verification in isolated containers.

Framework role:
- Provides scorer implementations that are "separated-mode aware":
  they produce a command to run in a verifier container and convert
  the container result into a ScoreMap.
- These scorers are NOT used in SHARED mode — the existing in-process
  scorers in ``snowl/scorer/agent.py`` handle that.

Runtime/usage wiring:
- The engine's ``score_trial_phase`` routes to these scorers when
  ``VerifierMode.SEPARATE`` is active and the scorer_id matches
  ``VerifierSpec.priority_scorers``.
- Registered in ``SEPARATED_SCORER_REGISTRY`` for lookup by scorer_id.

Change guardrails:
- Must not modify existing scorers in ``snowl/scorer/agent.py``.
- New scorers here delegate command execution to the verifier container.
"""

from __future__ import annotations

from typing import Any

from snowl.core.scorer import Score, ScoreContext
from snowl.runtime.separated_verifier import VerifierResult


class SeparatedCommandCheckScorer:
    """CommandCheckScorer variant for separated verifier execution.

    Instead of running ``subprocess.run()`` directly on the host,
    this scorer produces a command to be executed inside the verifier
    container and converts the result into a ScoreMap.
    """

    scorer_id: str = "command_check"
    metric_name: str = "command_check"

    def __init__(self, command: str | None = None, *, timeout_seconds: float = 30.0) -> None:
        self._command = command
        self._timeout_seconds = timeout_seconds

    def resolve_command(self, context: ScoreContext) -> str | None:
        """Extract the verification command from self or context metadata."""
        if self._command:
            return self._command
        meta = context.sample_metadata or {}
        return meta.get("verification_command") or meta.get("check_command")

    def score_from_result(self, result: VerifierResult) -> dict[str, Score]:
        """Convert a VerifierResult into a ScoreMap."""
        passed = result.exit_code == 0 and not result.timed_out
        explanation = (
            "Command check passed." if passed
            else f"Command check failed (exit_code={result.exit_code}, timed_out={result.timed_out})."
        )
        return {
            self.metric_name: Score(
                value=1.0 if passed else 0.0,
                explanation=explanation,
                metadata={
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "separated": True,
                    "container_id": result.container_id,
                    "stdout_tail": result.stdout[-2000:] if result.stdout else "",
                    "stderr_tail": result.stderr[-2000:] if result.stderr else "",
                },
            )
        }


class SeparatedWorkspaceDiffScorer:
    """WorkspaceDiffScorer variant for separated verifier execution.

    Runs a diff check command inside the verifier container to verify
    workspace changes against expected outcomes.
    """

    scorer_id: str = "workspace_diff"
    metric_name: str = "workspace_diff"

    def resolve_command(self, context: ScoreContext) -> str | None:
        """Build a command to check workspace state in the container."""
        meta = context.sample_metadata or {}
        check_cmd = meta.get("workspace_check_command")
        if check_cmd:
            return str(check_cmd)
        # Default: list files in /workspace and check for expected artifacts
        expected_files = meta.get("expected_files", [])
        if expected_files:
            checks = " && ".join(f'test -f "/workspace/{f}"' for f in expected_files)
            return checks
        return None

    def score_from_result(self, result: VerifierResult) -> dict[str, Score]:
        """Convert a VerifierResult into a ScoreMap."""
        passed = result.exit_code == 0 and not result.timed_out
        return {
            self.metric_name: Score(
                value=1.0 if passed else 0.0,
                explanation="Workspace diff check passed." if passed else "Workspace diff check failed.",
                metadata={
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "separated": True,
                    "container_id": result.container_id,
                },
            )
        }


# Registry: maps scorer_id → separated scorer class
SEPARATED_SCORER_REGISTRY: dict[str, type] = {
    "command_check": SeparatedCommandCheckScorer,
    "workspace_diff": SeparatedWorkspaceDiffScorer,
}


def get_separated_scorer(scorer_id: str) -> Any | None:
    """Look up a separated scorer class by scorer_id.

    Returns the class (not an instance) so callers can instantiate
    with context-specific parameters.
    """
    return SEPARATED_SCORER_REGISTRY.get(scorer_id)
