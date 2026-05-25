"""Tests for Hooks protocol, @hooks decorator, HooksBridge, and built-in hooks."""

import asyncio
import pytest

from snowl.core.hooks import (
    HooksBridge,
    RunContext,
    TrialContext,
    TrialHooks,
    _event_to_method,
    hooks,
)
from snowl.core.hooks_builtin import CostTrackerHook, AuditLogHook, ProgressHook
from snowl.core.declarations import get_declaration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_ctx(**kw):
    defaults = dict(run_id="r1", benchmark="test", experiment_id="", metadata={})
    defaults.update(kw)
    return RunContext(**defaults)


def _trial_ctx(**kw):
    defaults = dict(task_id="t1", agent_id="a1", variant_id="v1", sample_id=None, model=None, metadata={})
    defaults.update(kw)
    return TrialContext(**defaults)


# ---------------------------------------------------------------------------
# @hooks decorator
# ---------------------------------------------------------------------------

class TestHooksDecorator:
    def test_decorates_class(self):
        @hooks
        class MyHook:
            hooks_id = "my-hook"

        decl = get_declaration(MyHook)
        assert decl is not None
        assert decl.kind == "hooks"

    def test_decorates_with_id(self):
        @hooks(hooks_id="custom-id")
        class MyHook:
            hooks_id = "original"

        decl = get_declaration(MyHook)
        assert decl.object_id == "custom-id"

    def test_rejects_empty_id(self):
        from snowl.errors import SnowlValidationError
        with pytest.raises(SnowlValidationError, match="non-empty string"):
            @hooks(hooks_id="")
            class MyHook:
                hooks_id = "x"


# ---------------------------------------------------------------------------
# HooksBridge
# ---------------------------------------------------------------------------

class TestHooksBridge:
    @pytest.mark.asyncio
    async def test_dispatch_trial_start(self):
        called = []

        class Hook:
            hooks_id = "test"
            async def on_trial_start(self, context):
                called.append(("start", context.task_id))

        bridge = HooksBridge([Hook()])
        await bridge.dispatch("trial.start", context=_trial_ctx())
        assert called == [("start", "t1")]

    @pytest.mark.asyncio
    async def test_dispatch_runtime_prefixed_event(self):
        called = []

        class Hook:
            hooks_id = "test"
            async def on_trial_start(self, context):
                called.append(True)

        bridge = HooksBridge([Hook()])
        await bridge.dispatch("runtime.trial.start", context=_trial_ctx())
        assert called == [True]

    @pytest.mark.asyncio
    async def test_error_isolation(self):
        """A failing hook should not prevent others from running."""
        called = []

        class BadHook:
            hooks_id = "bad"
            async def on_trial_start(self, context):
                raise RuntimeError("boom")

        class GoodHook:
            hooks_id = "good"
            async def on_trial_start(self, context):
                called.append(True)

        bridge = HooksBridge([BadHook(), GoodHook()])
        await bridge.dispatch("trial.start", context=_trial_ctx())
        assert called == [True]

    @pytest.mark.asyncio
    async def test_unknown_event_ignored(self):
        class Hook:
            hooks_id = "test"
            async def on_trial_start(self, context):
                pass

        bridge = HooksBridge([Hook()])
        # Should not raise
        await bridge.dispatch("unknown.event", context=_trial_ctx())


# ---------------------------------------------------------------------------
# CostTrackerHook
# ---------------------------------------------------------------------------

class TestCostTrackerHook:
    @pytest.mark.asyncio
    async def test_accumulates_usage(self):
        hook = CostTrackerHook()
        ctx = _trial_ctx(model="gpt-4")

        await hook.on_model_usage(ctx, {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "estimated_cost_usd": 0.01})
        await hook.on_model_usage(ctx, {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300, "estimated_cost_usd": 0.02})

        assert hook.total_input_tokens == 300
        assert hook.total_output_tokens == 150
        assert hook.total_tokens == 450
        assert abs(hook.total_cost_usd - 0.03) < 0.001

    @pytest.mark.asyncio
    async def test_per_model_tracking(self):
        hook = CostTrackerHook()
        await hook.on_model_usage(_trial_ctx(model="gpt-4"), {"input_tokens": 100, "output_tokens": 0, "total_tokens": 100})
        await hook.on_model_usage(_trial_ctx(model="claude"), {"input_tokens": 50, "output_tokens": 0, "total_tokens": 50})

        assert "gpt-4" in hook._per_model
        assert "claude" in hook._per_model
        assert hook._per_model["gpt-4"]["input_tokens"] == 100

    def test_summary(self):
        hook = CostTrackerHook()
        hook.total_tokens = 100
        s = hook.summary()
        assert s["total_tokens"] == 100
        assert "per_model" in s


# ---------------------------------------------------------------------------
# AuditLogHook
# ---------------------------------------------------------------------------

class TestAuditLogHook:
    @pytest.mark.asyncio
    async def test_records_events(self):
        hook = AuditLogHook()
        ctx = _run_ctx()

        await hook.on_run_start(ctx)
        await hook.on_run_end(ctx, results=[])

        assert len(hook._entries) == 2
        assert hook._entries[0]["event"] == "run.start"
        assert hook._entries[1]["event"] == "run.end"

    @pytest.mark.asyncio
    async def test_trial_events(self):
        hook = AuditLogHook()
        tctx = _trial_ctx()

        await hook.on_trial_start(tctx)
        await hook.on_error(tctx, RuntimeError("test"))

        assert len(hook._entries) == 2
        assert hook._entries[1]["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# ProgressHook
# ---------------------------------------------------------------------------

class TestProgressHook:
    @pytest.mark.asyncio
    async def test_counts_trials(self):
        hook = ProgressHook(total_trials=3)
        ctx = _run_ctx()

        await hook.on_run_start(ctx)
        await hook.on_trial_end(_trial_ctx(), None)
        await hook.on_trial_end(_trial_ctx(), None)

        assert hook.completed_trials == 2
        assert hook.total_trials == 3

    @pytest.mark.asyncio
    async def test_counts_failures(self):
        hook = ProgressHook(total_trials=2)

        await hook.on_error(_trial_ctx(), RuntimeError("fail"))

        assert hook.completed_trials == 1
        assert hook.failed_trials == 1

    def test_summary(self):
        hook = ProgressHook(total_trials=10, completed_trials=5, failed_trials=1)
        s = hook.summary()
        assert s["completed_trials"] == 5
        assert s["failed_trials"] == 1
