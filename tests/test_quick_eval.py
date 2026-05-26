"""Tests for snowl.quick_eval — the one-call evaluation API."""

from __future__ import annotations

import pytest

from snowl.quick_eval import (
    QuickEvalResult,
    quick_eval,
    quick_eval_sync,
    _resolve_agent,
    _resolve_scorer,
)


# ---------------------------------------------------------------------------
# Agent normalization
# ---------------------------------------------------------------------------

class _DummyAgent:
    agent_id = "dummy"

    async def run(self, state, context, tools=None):
        from snowl.core import StopReason
        state.messages.append({"role": "assistant", "content": "ok"})
        state.stop_reason = StopReason.COMPLETED
        state.output = {
            "message": {"role": "assistant", "content": "ok"},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
        return state


def test_resolve_agent_from_callable():
    agent = _resolve_agent(lambda msgs, tools: "hello")
    assert agent.agent_id == "custom"


def test_resolve_agent_from_agent_instance():
    original = _DummyAgent()
    resolved = _resolve_agent(original)
    assert resolved is original


def test_resolve_agent_rejects_non_callable():
    with pytest.raises(TypeError, match="callable or an Agent instance"):
        _resolve_agent(42)


# ---------------------------------------------------------------------------
# Scorer normalization
# ---------------------------------------------------------------------------

def test_resolve_scorer_by_name():
    scorer = _resolve_scorer("includes")
    assert scorer is not None


def test_resolve_scorer_by_instance():
    from snowl.scorer import includes
    original = includes()
    resolved = _resolve_scorer(original)
    # Duck-typing check returns the same instance
    assert resolved is original


def test_resolve_scorer_none_returns_default():
    # None → defaults to "includes" inside quick_eval, but _resolve_scorer returns None
    assert _resolve_scorer(None) is None


def test_resolve_scorer_unknown_name():
    with pytest.raises(ValueError, match="Unknown scorer name"):
        _resolve_scorer("nonexistent_scorer")


# ---------------------------------------------------------------------------
# quick_eval with custom samples
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quick_eval_with_callable_and_samples():
    """Bare lambda + custom samples → QuickEvalResult."""
    result = await quick_eval(
        agent=lambda msgs, tools: "hello world",
        samples=[
            {"id": "s1", "input": "Say hello", "target": "hello"},
            {"id": "s2", "input": "Say hi", "target": "hi"},
        ],
        scorer="includes",
    )
    assert isinstance(result, QuickEvalResult)
    assert result.sample_count == 2
    assert result.total_tokens >= 0
    assert result.duration_ms >= 0
    assert "includes" in result.scores


@pytest.mark.asyncio
async def test_quick_eval_with_agent_instance():
    """Agent Protocol instance + custom samples."""
    result = await quick_eval(
        agent=_DummyAgent(),
        samples=[{"id": "s1", "input": "test"}],
        scorer="includes",
    )
    assert result.sample_count == 1
    assert result.status in {"success", "incorrect"}


def test_quick_eval_sync_wrapper():
    """quick_eval_sync works without await (must run outside existing event loop)."""
    result = quick_eval_sync(
        agent=lambda msgs, tools: "test",
        samples=[{"id": "s1", "input": "Say test", "target": "test"}],
        scorer="includes",
    )
    assert isinstance(result, QuickEvalResult)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quick_eval_requires_benchmark_or_samples():
    """Must provide either benchmark or samples."""
    with pytest.raises(ValueError, match="Provide either"):
        await quick_eval(agent=lambda m, t: "x")


@pytest.mark.asyncio
async def test_quick_eval_rejects_both_benchmark_and_samples():
    """Cannot provide both benchmark and samples."""
    with pytest.raises(ValueError, match="not both"):
        await quick_eval(
            agent=lambda m, t: "x",
            benchmark="strongreject",
            samples=[{"id": "s1", "input": "hi"}],
        )


# ---------------------------------------------------------------------------
# QuickEvalResult.__str__
# ---------------------------------------------------------------------------

def test_quick_eval_result_str():
    result = QuickEvalResult(
        status="success",
        pass_rate=0.75,
        scores={"includes": 0.75},
        total_tokens=100,
        duration_ms=500,
        sample_count=4,
    )
    text = str(result)
    assert "75% pass rate" in text
    assert "4 samples" in text
