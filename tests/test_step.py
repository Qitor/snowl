"""Tests for TaskStep model, StepResult model, and Task.steps integration."""

import pytest

from snowl.core.agent import AgentState
from snowl.core.env import EnvSpec
from snowl.core.step import TaskStep
from snowl.core.task import Task, validate_task
from snowl.core.task_result import StepResult, TaskResult, TaskStatus, Timing, Usage


# ---------------------------------------------------------------------------
# TaskStep
# ---------------------------------------------------------------------------

class TestTaskStep:
    def test_basic_creation(self):
        step = TaskStep(step_id="setup", instruction="Install nginx")
        assert step.step_id == "setup"
        assert step.instruction == "Install nginx"
        assert step.env_spec is None
        assert step.min_reward == 0.0
        assert step.scorer_ids == ()
        assert step.timeout_sec is None
        assert step.artifacts == ()

    def test_full_creation(self):
        env = EnvSpec(env_type="local", config={})
        step = TaskStep(
            step_id="execute",
            instruction="Run the test",
            env_spec=env,
            scorer_ids=("accuracy", "safety"),
            min_reward=0.8,
            timeout_sec=60.0,
            artifacts=("/tmp/result.json",),
            metadata={"priority": "high"},
        )
        assert step.env_spec is env
        assert step.min_reward == 0.8
        assert step.scorer_ids == ("accuracy", "safety")
        assert len(step.artifacts) == 1

    def test_frozen(self):
        step = TaskStep(step_id="s1", instruction="Do something")
        with pytest.raises(AttributeError):
            step.step_id = "s2"


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------

class TestStepResult:
    def test_basic_creation(self):
        result = StepResult(step_id="setup", status=TaskStatus.SUCCESS)
        assert result.step_id == "setup"
        assert result.status == TaskStatus.SUCCESS
        assert result.scores == {}
        assert result.max_score == 0.0
        assert result.timing is None
        assert result.usage is None

    def test_full_creation(self):
        result = StepResult(
            step_id="execute",
            status=TaskStatus.INCORRECT,
            scores={"accuracy": 0.5},
            max_score=0.5,
            timing=Timing(started_at_ms=1000, ended_at_ms=2000, duration_ms=1000),
            usage=Usage(input_tokens=100, output_tokens=50, total_tokens=150),
            artifacts={"output": "/tmp/result.json"},
        )
        assert result.max_score == 0.5
        assert result.timing.duration_ms == 1000
        assert result.usage.total_tokens == 150


# ---------------------------------------------------------------------------
# Task.steps integration
# ---------------------------------------------------------------------------

class TestTaskSteps:
    def _make_env(self):
        return EnvSpec(env_type="local", config={})

    def test_task_default_no_steps(self):
        task = Task(
            task_id="t1",
            env_spec=self._make_env(),
            sample_iter_factory=lambda: iter([{"input": "hello"}]),
        )
        assert task.steps == ()

    def test_task_with_steps(self):
        steps = (
            TaskStep(step_id="setup", instruction="Install deps"),
            TaskStep(step_id="run", instruction="Execute tests"),
        )
        task = Task(
            task_id="t1",
            env_spec=self._make_env(),
            sample_iter_factory=lambda: iter([{"input": "hello"}]),
            steps=steps,
        )
        assert len(task.steps) == 2
        assert task.steps[0].step_id == "setup"

    def test_validate_task_with_valid_steps(self):
        steps = (
            TaskStep(step_id="s1", instruction="Step 1"),
            TaskStep(step_id="s2", instruction="Step 2"),
        )
        task = Task(
            task_id="t1",
            env_spec=self._make_env(),
            sample_iter_factory=lambda: iter([{"input": "hello"}]),
            steps=steps,
        )
        validate_task(task)  # Should not raise

    def test_validate_task_rejects_duplicate_step_ids(self):
        from snowl.errors import SnowlValidationError
        steps = (
            TaskStep(step_id="dup", instruction="Step 1"),
            TaskStep(step_id="dup", instruction="Step 2"),
        )
        task = Task(
            task_id="t1",
            env_spec=self._make_env(),
            sample_iter_factory=lambda: iter([{"input": "hello"}]),
            steps=steps,
        )
        with pytest.raises(SnowlValidationError, match="Duplicate step_id"):
            validate_task(task)


# ---------------------------------------------------------------------------
# TaskResult.step_results integration
# ---------------------------------------------------------------------------

class TestTaskResultStepResults:
    def test_default_no_step_results(self):
        result = TaskResult(
            task_id="t1",
            agent_id="a1",
            sample_id="s1",
            seed=None,
            status=TaskStatus.SUCCESS,
        )
        assert result.step_results is None

    def test_with_step_results(self):
        step_results = [
            StepResult(step_id="s1", status=TaskStatus.SUCCESS, max_score=1.0),
            StepResult(step_id="s2", status=TaskStatus.INCORRECT, max_score=0.3),
        ]
        result = TaskResult(
            task_id="t1",
            agent_id="a1",
            sample_id="s1",
            seed=None,
            status=TaskStatus.INCORRECT,
            step_results=step_results,
        )
        assert len(result.step_results) == 2
        assert result.step_results[0].step_id == "s1"
        assert result.step_results[1].max_score == 0.3
