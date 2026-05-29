"""Verifier scorer that executes test scripts and reads reward values.

Framework role:
- Provides a scorer that delegates verification to an external test script,
  reading a numeric reward from a file inside the environment.
- Supports both reward.txt (single float) and reward.json (multi-dimension) formats.
- In SEPARATE mode, delegates to SeparatedVerifierExecutor.

Runtime/usage wiring:
- Registered as ``verifier`` in the scorer resolve registry.
- Used by code benchmarks where executable tests are more reliable than LLM judges.

Change guardrails:
- Must not modify existing scorers in ``snowl/scorer/agent.py``.
- SEPARATE mode delegates to existing infrastructure.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from snowl.core.scorer import Score, ScoreContext
from snowl.core.task_result import TaskResult
from snowl.errors import SnowlValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifierReport:
    """Standardized verifier output with confidence assessment.

    Attributes:
        score: Primary numeric reward (0.0–1.0).
        dimensions: Per-dimension scores when reward.json provides them.
        confidence: Reliability indicator: HIGH (clear pass/fail), MEDIUM (partial),
            LOW (infrastructure issue or timeout).
        environment_diff: Differences between agent and verifier environments, if available.
        raw_output: Raw stdout/stderr from the verifier command.
        retries_used: Number of infrastructure retries used during execution.
    """

    score: float
    dimensions: dict[str, float] | None = None
    confidence: str = "HIGH"
    environment_diff: dict[str, Any] | None = None
    raw_output: str | None = None
    retries_used: int = 0

    def to_metadata(self) -> dict[str, Any]:
        """Convert to a metadata dict suitable for Score.metadata."""
        d: dict[str, Any] = {"verifier_report": True, "confidence": self.confidence}
        if self.dimensions is not None:
            d["dimensions"] = dict(self.dimensions)
        if self.environment_diff is not None:
            d["environment_diff"] = dict(self.environment_diff)
        if self.raw_output is not None:
            d["raw_output"] = self.raw_output[:2000]
        if self.retries_used > 0:
            d["retries_used"] = self.retries_used
        return d


def _assess_confidence(score: float, timed_out: bool, retries_used: int = 0) -> str:
    """Assess verifier result confidence.

    HIGH: clear pass/fail (0.0 or 1.0) with no infrastructure issues.
    MEDIUM: partial score (between 0 and 1).
    LOW: timeout or infrastructure retry occurred.
    """
    if timed_out or retries_used > 0:
        return "LOW"
    if score == 0.0 or score == 1.0:
        return "HIGH"
    return "MEDIUM"


class VerifierScorer:
    """Execute a verification script in the environment and read the reward.

    Follows the Harbor verifier pattern:
    1. Upload test script to the environment (if needed)
    2. Execute the test command
    3. Read reward from ``reward_path`` (either .txt or .json)

    In SHARED mode (default), executes the command via sample_metadata
    environment handle. In SEPARATE mode, delegates to
    SeparatedVerifierExecutor.
    """

    scorer_id: str = "verifier"

    def __init__(
        self,
        test_command: str = "bash tests/test.sh",
        reward_path: str = "/logs/verifier/reward.txt",
        *,
        timeout_seconds: float = 120.0,
        strict: bool = False,
    ) -> None:
        self._test_command = test_command
        self._reward_path = reward_path
        self._timeout_seconds = timeout_seconds
        self._strict = strict

    async def ascore(
        self,
        task_result: TaskResult,
        trace: dict[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Execute verification and read reward."""
        # Check for SEPARATE mode via task_metadata
        verifier_mode = (context.task_metadata or {}).get("verifier_mode", "shared")
        if verifier_mode == "separate":
            return await self._score_separate(task_result, trace, context)
        return await self._score_shared(task_result, trace, context)

    async def _score_shared(
        self,
        task_result: TaskResult,
        trace: dict[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score in SHARED mode: execute command via environment handle."""
        meta = context.sample_metadata or {}

        # Try to get environment exec function from context
        env_exec = meta.get("environment_exec")
        env_read_file = meta.get("environment_read_file")

        # Execute test command
        exec_result: dict[str, Any] = {}
        if env_exec and callable(env_exec):
            exec_result = await env_exec(
                self._test_command,
                timeout_seconds=self._timeout_seconds,
            )

        exit_code = exec_result.get("exit_code", -1)
        timed_out = exec_result.get("timed_out", False)

        # Read reward
        reward_value = 0.0
        extra: dict[str, Any] = {}

        if env_read_file and callable(env_read_file):
            try:
                content = await env_read_file(self._reward_path)
                reward_value, extra = _parse_reward(content, self._reward_path)
            except Exception as exc:
                extra["reward_read_error"] = str(exc)
                if self._strict:
                    raise
        elif exit_code == 0 and not timed_out:
            # No file reader but command passed — assume success
            reward_value = 1.0

        report = _build_report(reward_value, timed_out=timed_out, extra_metadata=extra)
        reward_metadata: dict[str, Any] = {
            "test_command": self._test_command,
            "reward_path": self._reward_path,
            "exit_code": exit_code,
            "timed_out": timed_out,
            **extra,
            **report.to_metadata(),
        }

        return {
            "verifier": Score(
                value=reward_value,
                explanation=f"Verifier reward: {reward_value} (confidence: {report.confidence})" if reward_value else "Verifier failed.",
                metadata=reward_metadata,
            )
        }

    async def _score_separate(
        self,
        task_result: TaskResult,
        trace: dict[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Score in SEPARATE mode: delegate to SeparatedVerifierExecutor."""
        from snowl.runtime.separated_verifier import SeparatedVerifierExecutor
        from snowl.core.env import VerifierMode, VerifierSpec

        meta = context.task_metadata or {}
        verifier_spec_dict = meta.get("verifier_spec", {})
        if isinstance(verifier_spec_dict, dict):
            from snowl.runtime.separated_verifier import verifier_spec_from_config
            spec = verifier_spec_from_config(verifier_spec_dict)
        else:
            spec = verifier_spec_dict

        if spec is None or spec.mode != VerifierMode.SEPARATE:
            # Fallback to shared
            return await self._score_shared(task_result, trace, context)

        executor = SeparatedVerifierExecutor(
            spec=spec,
            run_id=meta.get("run_id"),
            trial_id=meta.get("trial_id"),
        )

        try:
            # Full lifecycle
            result = await executor.execute(
                self._test_command,
                workspace_dir=meta.get("workspace_dir"),
            )

            # Read reward from container
            reward_value = 0.0
            extra: dict[str, Any] = {}

            if result.exit_code == 0 and not result.timed_out:
                # Try to parse reward from stdout
                stdout = result.stdout or ""
                if stdout.strip():
                    try:
                        reward_value, extra = _parse_reward(stdout, self._reward_path)
                    except Exception:
                        reward_value = 1.0  # Command passed, default reward
                else:
                    reward_value = 1.0

            report = _build_report(
                reward_value,
                timed_out=result.timed_out,
                retries_used=executor._retries_used,
                extra_metadata=extra,
                raw_output=result.stdout,
            )
            reward_metadata: dict[str, Any] = {
                "test_command": self._test_command,
                "reward_path": self._reward_path,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "container_id": result.container_id,
                "separated": True,
                **extra,
                **report.to_metadata(),
            }

            return {
                "verifier": Score(
                    value=reward_value,
                    explanation=f"Verifier reward: {reward_value} (confidence: {report.confidence})" if reward_value else "Verifier failed.",
                    metadata=reward_metadata,
                )
            }
        except Exception as exc:
            logger.warning("VerifierScorer SEPARATE mode failed: %s", exc)
            return {
                "verifier": Score(
                    value=0.0,
                    explanation=f"Verifier error: {exc}",
                    metadata={"error": str(exc), "separated": True},
                )
            }

    def score(
        self,
        task_result: TaskResult,
        trace: dict[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        """Sync wrapper for ascore (runs in thread via SyncScorerAdapter)."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context — create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.ascore(task_result, trace, context),
                )
                return future.result(timeout=self._timeout_seconds + 30)
        else:
            return asyncio.run(self.ascore(task_result, trace, context))


def _parse_reward(content: str, path: str) -> tuple[float, dict[str, Any]]:
    """Parse reward from file content.

    Supports:
    - reward.txt: single float on a line
    - reward.json: {"reward": float} or {"dimensions": {"name": float, ...}}

    Returns:
        Tuple of (reward_value, extra_metadata).
    """
    content = content.strip()
    if not content:
        return 0.0, {"reward_empty": True}

    # Try JSON first
    if path.endswith(".json") or content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if "reward" in data:
                    return float(data["reward"]), {"reward_json": data}
                if "dimensions" in data:
                    dims = data["dimensions"]
                    if isinstance(dims, dict):
                        avg = sum(dims.values()) / len(dims) if dims else 0.0
                        return avg, {"reward_dimensions": dims, "reward_json": data}
            return 0.0, {"reward_json": data}
        except (json.JSONDecodeError, ValueError):
            pass

    # Try single float
    try:
        return float(content), {"reward_text": content}
    except ValueError:
        # Try last line
        lines = content.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    return float(line), {"reward_text": line}
                except ValueError:
                    continue

    return 0.0, {"reward_parse_failed": True, "raw_content": content[:200]}


def _build_report(
    reward_value: float,
    *,
    timed_out: bool = False,
    retries_used: int = 0,
    extra_metadata: dict[str, Any] | None = None,
    raw_output: str | None = None,
) -> VerifierReport:
    """Build a VerifierReport from raw reward value with confidence assessment."""
    dimensions = None
    if extra_metadata and "reward_dimensions" in extra_metadata:
        dimensions = extra_metadata["reward_dimensions"]

    confidence = _assess_confidence(reward_value, timed_out, retries_used)

    return VerifierReport(
        score=reward_value,
        dimensions=dimensions,
        confidence=confidence,
        raw_output=raw_output,
        retries_used=retries_used,
    )
