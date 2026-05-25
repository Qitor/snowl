"""Tests for RateLimitAlertHook."""

import pytest

from snowl.core.hooks import RunContext, TrialContext
from snowl.core.hooks_builtin import RateLimitAlertHook


def _trial_ctx(**overrides):
    defaults = dict(task_id="t1", agent_id="a1", variant_id="v1")
    defaults.update(overrides)
    return TrialContext(**defaults)


def _run_ctx(**overrides):
    defaults = dict(run_id="r1", benchmark="test")
    defaults.update(overrides)
    return RunContext(**defaults)


class TestRateLimitAlertHook:
    def test_hooks_id(self):
        hook = RateLimitAlertHook()
        assert hook.hooks_id == "rate-limit-alert"

    def test_default_threshold(self):
        hook = RateLimitAlertHook()
        assert hook.warn_after == 3

    def test_custom_threshold(self):
        hook = RateLimitAlertHook(warn_after=5, window_seconds=120)
        assert hook.warn_after == 5
        assert hook.window_seconds == 120.0

    @pytest.mark.asyncio
    async def test_on_error_rate_limit_detected(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("rate limit exceeded"))
        assert hook._total_rate_limits == 1

    @pytest.mark.asyncio
    async def test_on_error_429_detected(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("HTTP 429 Too Many Requests"))
        assert hook._total_rate_limits == 1

    @pytest.mark.asyncio
    async def test_on_error_non_rate_limit_ignored(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("connection timeout"))
        assert hook._total_rate_limits == 0

    @pytest.mark.asyncio
    async def test_alert_triggered_after_threshold(self):
        hook = RateLimitAlertHook(warn_after=2)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("rate limit"))
        assert len(hook._alerts) == 0
        await hook.on_error(ctx, RuntimeError("rate limit"))
        assert len(hook._alerts) == 1

    @pytest.mark.asyncio
    async def test_window_reset(self):
        hook = RateLimitAlertHook(warn_after=2, window_seconds=0.001)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("rate limit"))
        # Wait for window to expire
        import asyncio
        await asyncio.sleep(0.01)
        await hook.on_error(ctx, RuntimeError("rate limit"))
        # Window reset, so count should be 1 in new window — no alert yet
        assert hook._total_rate_limits == 2

    @pytest.mark.asyncio
    async def test_model_usage_rate_limited(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx(model="gpt-4")
        await hook.on_model_usage(ctx, {"rate_limited": True, "retry_after_ms": 5000})
        assert hook._total_rate_limits == 1

    @pytest.mark.asyncio
    async def test_model_usage_normal(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx(model="gpt-4")
        await hook.on_model_usage(ctx, {"input_tokens": 100})
        assert hook._total_rate_limits == 0

    @pytest.mark.asyncio
    async def test_summary(self):
        hook = RateLimitAlertHook(warn_after=1)
        ctx = _trial_ctx()
        await hook.on_error(ctx, RuntimeError("rate limit"))
        summary = hook.summary()
        assert summary["total_rate_limits"] == 1
        assert "alerts" in summary
