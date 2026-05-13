"""Tests for the AsyncScorer protocol, SyncScorerAdapter, and runtime dispatch."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import pytest

from snowl.core import (
    AsyncScorer,
    Score,
    ScoreContext,
    Scorer,
    SyncScorerAdapter,
    is_async_scorer,
    validate_async_scorer,
    validate_scorer,
)
from snowl.core.task_result import TaskResult
from snowl.errors import SnowlValidationError


def _make_task_result(**overrides: Any) -> TaskResult:
    defaults = {
        "task_id": "t1",
        "agent_id": "a1",
        "sample_id": "s1",
        "seed": 1,
        "status": "SUCCESS",
        "final_output": {},
        "timing": None,
        "usage": None,
        "error": None,
        "artifacts": [],
        "payload": {},
    }
    defaults.update(overrides)
    return TaskResult(**defaults)


def _make_score_context(**overrides: Any) -> ScoreContext:
    defaults = {
        "task_id": "t1",
        "agent_id": "a1",
        "sample_id": "s1",
        "task_metadata": {},
        "sample_metadata": {},
    }
    defaults.update(overrides)
    return ScoreContext(**defaults)


# ---------------------------------------------------------------------------
# SyncScorerAdapter
# ---------------------------------------------------------------------------


class _StubSyncScorer:
    scorer_id = "stub_sync"

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        return {"stub_metric": Score(value=1.0, explanation="stub")}


@pytest.mark.asyncio
async def test_sync_scorer_adapter_wraps_sync_scorer():
    inner = _StubSyncScorer()
    adapter = SyncScorerAdapter(inner)
    assert adapter.scorer_id == "stub_sync"
    result = await adapter.ascore(
        _make_task_result(),
        {"trace_events": []},
        _make_score_context(),
    )
    assert "stub_metric" in result
    assert result["stub_metric"].value == 1.0


def test_sync_scorer_adapter_preserves_scorer_id():
    inner = _StubSyncScorer()
    inner.scorer_id = "custom_id"
    adapter = SyncScorerAdapter(inner)
    assert adapter.scorer_id == "custom_id"


def test_sync_scorer_adapter_fallback_scorer_id():
    """If inner has no scorer_id, adapter falls back to 'sync_adapter'."""

    class _NoIdScorer:
        def score(self, task_result, trace, context):
            return {"x": Score(value=0.0)}

    adapter = SyncScorerAdapter(_NoIdScorer())
    assert adapter.scorer_id == "sync_adapter"


# ---------------------------------------------------------------------------
# is_async_scorer
# ---------------------------------------------------------------------------


def test_is_async_scorer_detects_ascore():
    class _AsyncImpl:
        scorer_id = "async_test"

        async def ascore(self, task_result, trace, context):
            return {"m": Score(value=0.5)}

    assert is_async_scorer(_AsyncImpl()) is True


def test_is_async_scorer_returns_false_for_sync_only():
    assert is_async_scorer(_StubSyncScorer()) is False


def test_is_async_scorer_returns_false_for_plain_object():
    assert is_async_scorer(object()) is False


def test_is_async_scorer_returns_true_for_both_protocols():
    """A scorer with both score() and ascore() is recognized as async."""

    class _DualScorer:
        scorer_id = "dual"

        def score(self, task_result, trace, context):
            return {"m": Score(value=0.5)}

        async def ascore(self, task_result, trace, context):
            return {"m": Score(value=0.5)}

    assert is_async_scorer(_DualScorer()) is True


# ---------------------------------------------------------------------------
# validate_async_scorer
# ---------------------------------------------------------------------------


def test_validate_async_scorer_ok():
    class _Ok:
        scorer_id = "ok"
        async def ascore(self, task_result, trace, context):
            return {}

    validate_async_scorer(_Ok())  # no error


def test_validate_async_scorer_missing_id():
    class _Bad:
        async def ascore(self, task_result, trace, context):
            return {}

    with pytest.raises(SnowlValidationError, match="scorer_id"):
        validate_async_scorer(_Bad())


def test_validate_async_scorer_missing_ascore():
    class _Bad:
        scorer_id = "bad"

    with pytest.raises(SnowlValidationError, match="ascore"):
        validate_async_scorer(_Bad())


# ---------------------------------------------------------------------------
# Runtime dispatch: score_trial_phase integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_trial_phase_uses_ascore_for_async_scorer():
    """Verify that score_trial_phase calls ascore when available."""
    from snowl.runtime.engine import score_trial_phase, PartialTrialResult, PreparedTrial
    from snowl.core import EnvSpec, Task, AgentState, StopReason, TaskStatus

    scored_via_ascore = False

    class _AsyncScorerImpl:
        scorer_id = "async_dispatch_test"

        async def ascore(self, task_result, trace, context):
            nonlocal scored_via_ascore
            scored_via_ascore = True
            return {"m": Score(value=0.9, explanation="async")}

    task_result = _make_task_result(status=TaskStatus.SUCCESS)
    trace: dict[str, Any] = {"trace_events": []}
    score_context = _make_score_context()

    partial = PartialTrialResult(
        task_result=task_result,
        trace=trace,
        score_context=score_context,
    )

    from snowl.runtime.engine import TrialRequest, TrialLimits, ContainerPrepareResult
    from snowl.runtime.container_runtime import ContainerRuntime

    sample = {"id": "s1", "input": "hello", "metadata": {}}
    task_obj = Task(
        task_id="t1",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([sample]),
        metadata={},
    )

    class _MinimalAgent:
        agent_id = "minimal"
        variant_id = "v1"
        model = "test"

        async def run(self, state, context, tools=None):
            return state

    request = TrialRequest(
        task=task_obj,
        agent=_MinimalAgent(),
        scorer=_AsyncScorerImpl(),
        sample=sample,
    )

    prepared = PreparedTrial(
        request=request,
        started_ms=0,
        sample_id="s1",
        variant_id="v1",
        variant_model="test",
        state=AgentState(messages=[]),
        context=None,  # type: ignore
        resolved_tool_specs=[],
        sandbox_runtime=None,  # type: ignore
        container_runtime=None,  # type: ignore
        container_prepare=ContainerPrepareResult(
            session=None, requires_container=False, requires_build=False,
            spec_hash=None, prepare_provider_ids=(), metadata={},
        ),
    )

    outcome = await score_trial_phase(prepared, partial)
    assert scored_via_ascore is True
    assert "m" in outcome.scores
    assert outcome.scores["m"].value == 0.9
