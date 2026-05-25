"""Tests for IPI Coding Agent multi-step task support."""

from snowl.benchmarks.ipi_coding_agent.adapter import IPICodingAgentBenchmarkAdapter
from snowl.core.step import TaskStep


class TestIPIMultiStep:
    def test_load_tasks_has_steps(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "issue_text": "Login fails on special chars",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        assert len(tasks) == 1
        assert len(tasks[0].steps) == 3

    def test_step_ids(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        step_ids = [s.step_id for s in tasks[0].steps]
        assert step_ids == ["setup", "execute", "verify"]

    def test_steps_are_task_step_instances(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        for step in tasks[0].steps:
            assert isinstance(step, TaskStep)

    def test_verify_step_has_scorer(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        verify_step = tasks[0].steps[2]
        assert verify_step.step_id == "verify"
        assert "ipi_coding_agent" in verify_step.scorer_ids

    def test_verify_step_has_min_reward(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        verify_step = tasks[0].steps[2]
        assert verify_step.min_reward == 0.5

    def test_steps_have_env_spec(self):
        adapter = IPICodingAgentBenchmarkAdapter(
            rows=[{
                "id": "test-1",
                "task_description": "Fix the login bug",
                "is_benign": True,
            }]
        )
        tasks = adapter.load_tasks(split="test")
        for step in tasks[0].steps:
            assert step.env_spec is not None
