"""Tests for MultiStepExecutor and engine multi-step integration."""

import asyncio
import pytest

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason
from snowl.core.env import EnvSpec
from snowl.core.step import TaskStep
from snowl.core.task import Task
from snowl.core.task_result import TaskStatus
from snowl.runtime.multi_step import MultiStepExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SimpleAgent:
    """Agent that appends its agent_id and marks completed."""
    agent_id = "simple"

    async def run(self, state, context, tools=None):
        state.messages.append({"role": "assistant", "content": f"step done by {self.agent_id}"})
        state.stop_reason = StopReason.COMPLETED
        state.output = {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        return state


def _make_context():
    return AgentContext(task_id="test", sample_id="s1", metadata={})


def _make_env():
    return EnvSpec(env_type="local", config={})


# ---------------------------------------------------------------------------
# MultiStepExecutor
# ---------------------------------------------------------------------------

class TestMultiStepExecutor:
    @pytest.mark.asyncio
    async def test_single_step_execution(self):
        steps = (TaskStep(step_id="only", instruction="Do it"),)
        task = Task(
            task_id="t1",
            env_spec=_make_env(),
            sample_iter_factory=lambda: iter([{"input": "start"}]),
            steps=steps,
        )
        executor = MultiStepExecutor()
        results = await executor.execute(task, _SimpleAgent(), {"input": "start"}, _make_context())
        assert len(results) == 1
        assert results[0].step_id == "only"
        assert results[0].status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_multi_step_execution(self):
        steps = (
            TaskStep(step_id="setup", instruction="Install deps"),
            TaskStep(step_id="run", instruction="Execute tests"),
            TaskStep(step_id="verify", instruction="Check results"),
        )
        task = Task(
            task_id="t1",
            env_spec=_make_env(),
            sample_iter_factory=lambda: iter([{"input": "start"}]),
            steps=steps,
        )
        executor = MultiStepExecutor()
        results = await executor.execute(task, _SimpleAgent(), {"input": "start"}, _make_context())
        assert len(results) == 3
        assert [r.step_id for r in results] == ["setup", "run", "verify"]
        for r in results:
            assert r.status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_early_exit_on_min_reward(self):
        """If a step doesn't meet min_reward, subsequent steps are skipped."""
        class _FailingAgent:
            agent_id = "fail"
            async def run(self, state, context, tools=None):
                state.stop_reason = StopReason.COMPLETED
                # No usage data -> max_score stays 0
                state.output = {}
                return state

        steps = (
            TaskStep(step_id="step1", instruction="Do it", min_reward=0.5),
            TaskStep(step_id="step2", instruction="Should be skipped"),
        )
        task = Task(
            task_id="t1",
            env_spec=_make_env(),
            sample_iter_factory=lambda: iter([{"input": "start"}]),
            steps=steps,
        )
        executor = MultiStepExecutor()
        results = await executor.execute(task, _FailingAgent(), {"input": "start"}, _make_context())
        assert len(results) == 1
        assert results[0].step_id == "step1"

    @pytest.mark.asyncio
    async def test_step_timing_and_usage(self):
        steps = (TaskStep(step_id="s1", instruction="Do it"),)
        task = Task(
            task_id="t1",
            env_spec=_make_env(),
            sample_iter_factory=lambda: iter([{"input": "start"}]),
            steps=steps,
        )
        executor = MultiStepExecutor()
        results = await executor.execute(task, _SimpleAgent(), {"input": "start"}, _make_context())
        assert results[0].timing is not None
        assert results[0].timing.duration_ms >= 0
        assert results[0].usage is not None
        assert results[0].usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_messages_accumulate_across_steps(self):
        """Each step should see messages from previous steps."""
        class _TrackingAgent:
            agent_id = "tracker"
            async def run(self, state, context, tools=None):
                state.messages.append({"role": "assistant", "content": f"saw {len(state.messages)} msgs"})
                state.stop_reason = StopReason.COMPLETED
                state.output = {}
                return state

        steps = (
            TaskStep(step_id="s1", instruction="Step 1"),
            TaskStep(step_id="s2", instruction="Step 2"),
        )
        task = Task(
            task_id="t1",
            env_spec=_make_env(),
            sample_iter_factory=lambda: iter([{"input": "start"}]),
            steps=steps,
        )
        executor = MultiStepExecutor()
        results = await executor.execute(task, _TrackingAgent(), {"input": "start"}, _make_context())
        assert len(results) == 2
