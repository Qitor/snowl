"""Built-in hooks for cost tracking, audit logging, progress reporting, and rate-limit alerting.

Framework role:
- Provides ready-to-use hooks that compose with the eval lifecycle.
- ``CostTrackerHook`` accumulates model API costs across a run.
- ``AuditLogHook`` writes structured audit entries for each trial event.
- ``ProgressHook`` tracks trial completion progress.
- ``RateLimitAlertHook`` monitors API rate-limit responses and alerts when thresholds are approached.

Runtime/usage wiring:
- Registered via ``@hooks`` decorator or declared in ``project.yml``.
- Dispatched by ``HooksBridge`` from RunEventBus events.

Change guardrails:
- Must only import from ``snowl.core`` and stdlib.
- Hook methods must not raise — errors are logged and swallowed.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.core.hooks import RunContext, TrialContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CostTrackerHook
# ---------------------------------------------------------------------------

@dataclass
class CostTrackerHook:
    """Accumulate model API costs across a run.

    Usage::

        @hooks(hooks_id="cost-tracker")
        class MyCostTracker(CostTrackerHook):
            pass

    Or directly::

        cost_hook = CostTrackerHook()
    """

    hooks_id: str = "cost-tracker"
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    _per_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def on_run_start(self, context: RunContext) -> None:
        logger.info("CostTracker: run %s started", context.run_id)

    async def on_model_usage(self, context: TrialContext, usage: dict[str, Any]) -> None:
        input_t = int(usage.get("input_tokens", 0) or 0)
        output_t = int(usage.get("output_tokens", 0) or 0)
        total_t = int(usage.get("total_tokens", 0) or 0)
        cost = float(usage.get("estimated_cost_usd", 0.0) or 0.0)

        self.total_input_tokens += input_t
        self.total_output_tokens += output_t
        self.total_tokens += total_t
        self.total_cost_usd += cost

        model = context.model or "unknown"
        if model not in self._per_model:
            self._per_model[model] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        m = self._per_model[model]
        m["input_tokens"] += input_t
        m["output_tokens"] += output_t
        m["total_tokens"] += total_t
        m["cost_usd"] += cost

    async def on_run_end(self, context: RunContext, results: list[Any]) -> None:
        logger.info(
            "CostTracker: run %s ended — %d input, %d output, %d total tokens, $%.4f",
            context.run_id, self.total_input_tokens, self.total_output_tokens,
            self.total_tokens, self.total_cost_usd,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "per_model": dict(self._per_model),
        }


# ---------------------------------------------------------------------------
# AuditLogHook
# ---------------------------------------------------------------------------

@dataclass
class AuditLogHook:
    """Write structured audit log entries for trial lifecycle events.

    Each hook call appends a JSON line to the audit log file.
    """

    hooks_id: str = "audit-log"
    log_path: str = ""
    _entries: list[dict[str, Any]] = field(default_factory=list)

    def _append(self, entry: dict[str, Any]) -> None:
        entry["ts_ms"] = int(time.time() * 1000)
        self._entries.append(entry)
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception as exc:
                logger.warning("AuditLogHook: failed to write to %s: %s", self.log_path, exc)

    async def on_run_start(self, context: RunContext) -> None:
        self._append({"event": "run.start", "run_id": context.run_id, "benchmark": context.benchmark})

    async def on_run_end(self, context: RunContext, results: list[Any]) -> None:
        self._append({"event": "run.end", "run_id": context.run_id, "result_count": len(results)})

    async def on_trial_start(self, context: TrialContext) -> None:
        self._append({
            "event": "trial.start", "task_id": context.task_id,
            "agent_id": context.agent_id, "variant_id": context.variant_id,
        })

    async def on_trial_end(self, context: TrialContext, result: Any) -> None:
        status = getattr(result, "status", None)
        self._append({
            "event": "trial.end", "task_id": context.task_id,
            "agent_id": context.agent_id, "variant_id": context.variant_id,
            "status": str(status) if status else None,
        })

    async def on_error(self, context: TrialContext, error: Exception) -> None:
        self._append({
            "event": "trial.error", "task_id": context.task_id,
            "agent_id": context.agent_id, "error_type": type(error).__name__,
            "error_message": str(error),
        })

    async def on_score(self, context: TrialContext, scores: dict[str, Any]) -> None:
        self._append({
            "event": "trial.score", "task_id": context.task_id,
            "agent_id": context.agent_id, "scores": {k: str(v) for k, v in scores.items()},
        })

    async def on_model_usage(self, context: TrialContext, usage: dict[str, Any]) -> None:
        self._append({
            "event": "model.usage", "task_id": context.task_id,
            "model": context.model, "total_tokens": usage.get("total_tokens", 0),
        })


# ---------------------------------------------------------------------------
# ProgressHook
# ---------------------------------------------------------------------------

@dataclass
class ProgressHook:
    """Track and report trial completion progress.

    Useful for CLI progress bars and web monitor integration.
    """

    hooks_id: str = "progress"
    total_trials: int = 0
    completed_trials: int = 0
    failed_trials: int = 0
    _started_at_ms: int = 0

    async def on_run_start(self, context: RunContext) -> None:
        self._started_at_ms = int(time.time() * 1000)
        logger.info("ProgressHook: run started")

    async def on_trial_end(self, context: TrialContext, result: Any) -> None:
        self.completed_trials += 1
        status = getattr(result, "status", None)
        if status and str(status) == "error":
            self.failed_trials += 1
        self._log_progress()

    async def on_error(self, context: TrialContext, error: Exception) -> None:
        self.failed_trials += 1
        self.completed_trials += 1
        self._log_progress()

    async def on_run_end(self, context: RunContext, results: list[Any]) -> None:
        elapsed = int(time.time() * 1000) - self._started_at_ms
        logger.info(
            "ProgressHook: run completed — %d/%d trials (%d failed) in %dms",
            self.completed_trials, self.total_trials, self.failed_trials, elapsed,
        )

    def _log_progress(self) -> None:
        if self.total_trials > 0:
            pct = self.completed_trials / self.total_trials * 100
            logger.info(
                "Progress: %d/%d (%.0f%%) — %d failed",
                self.completed_trials, self.total_trials, pct, self.failed_trials,
            )

    def summary(self) -> dict[str, Any]:
        return {
            "total_trials": self.total_trials,
            "completed_trials": self.completed_trials,
            "failed_trials": self.failed_trials,
        }


# ---------------------------------------------------------------------------
# RateLimitAlertHook
# ---------------------------------------------------------------------------

@dataclass
class RateLimitAlertHook:
    """Monitor API rate-limit responses and alert when thresholds are approached.

    Tracks 429 / rate-limit errors from model API calls and emits warnings
    when the count exceeds a configurable threshold within a time window.

    Usage::

        @hooks(hooks_id="rate-limit-alert")
        class MyRateLimitAlert(RateLimitAlertHook):
            pass

    Or directly::

        rate_hook = RateLimitAlertHook(warn_after=3, window_seconds=60)
    """

    hooks_id: str = "rate-limit-alert"
    warn_after: int = 3
    window_seconds: float = 60.0
    _rate_limit_count: int = 0
    _total_rate_limits: int = 0
    _window_start_ms: int = 0
    _alerts: list[dict[str, Any]] = field(default_factory=list)

    def _check_window(self) -> None:
        now_ms = int(time.time() * 1000)
        if self._window_start_ms == 0:
            self._window_start_ms = now_ms
        elapsed = now_ms - self._window_start_ms
        if elapsed > self.window_seconds * 1000:
            # Reset window
            self._rate_limit_count = 0
            self._window_start_ms = now_ms

    async def on_run_start(self, context: RunContext) -> None:
        self._window_start_ms = int(time.time() * 1000)
        logger.info("RateLimitAlertHook: monitoring started (warn_after=%d, window=%.0fs)",
                     self.warn_after, self.window_seconds)

    async def on_error(self, context: TrialContext, error: Exception) -> None:
        error_msg = str(error).lower()
        error_type = type(error).__name__.lower()
        is_rate_limit = (
            "rate" in error_msg and "limit" in error_msg
        ) or "429" in error_msg or "ratelimit" in error_type

        if is_rate_limit:
            self._check_window()
            self._rate_limit_count += 1
            self._total_rate_limits += 1

            if self._rate_limit_count >= self.warn_after:
                alert = {
                    "event": "rate_limit_alert",
                    "task_id": context.task_id,
                    "agent_id": context.agent_id,
                    "count_in_window": self._rate_limit_count,
                    "total_count": self._total_rate_limits,
                    "warn_after": self.warn_after,
                    "window_seconds": self.window_seconds,
                }
                self._alerts.append(alert)
                logger.warning(
                    "RateLimitAlertHook: %d rate-limit errors in %.0fs window "
                    "(threshold=%d). Consider reducing concurrency or adding delays.",
                    self._rate_limit_count, self.window_seconds, self.warn_after,
                )

    async def on_model_usage(self, context: TrialContext, usage: dict[str, Any]) -> None:
        # Also check for rate-limit signals in usage metadata
        rate_limited = usage.get("rate_limited", False)
        retry_after = usage.get("retry_after_ms")
        if rate_limited:
            self._check_window()
            self._rate_limit_count += 1
            self._total_rate_limits += 1
            if self._rate_limit_count >= self.warn_after:
                logger.warning(
                    "RateLimitAlertHook: rate-limited call detected for model %s "
                    "(retry_after=%sms, count=%d/%d)",
                    context.model, retry_after, self._rate_limit_count, self.warn_after,
                )

    async def on_run_end(self, context: RunContext, results: list[Any]) -> None:
        logger.info(
            "RateLimitAlertHook: run ended — %d total rate-limit events, %d alerts",
            self._total_rate_limits, len(self._alerts),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "total_rate_limits": self._total_rate_limits,
            "alerts": len(self._alerts),
            "alert_details": self._alerts,
        }
