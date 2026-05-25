"""Tests for multi-step result display in console renderer."""

from dataclasses import dataclass
from typing import Any

from snowl.core.task_result import StepResult, TaskStatus, TaskResult, Timing


@dataclass
class MockOutcome:
    task_result: Any
    trace: dict


class TestMultiStepDisplay:
    """Verify ConsoleRenderer.render_trial_finish shows step results."""

    def _make_step_result(self, step_id, status, max_score=0.0):
        return StepResult(
            step_id=step_id,
            status=status,
            max_score=max_score,
        )

    def test_step_results_rendered_in_output(self, capsys):
        from snowl.ui.console import ConsoleRenderer
        renderer = ConsoleRenderer(verbose=True)

        step_results = [
            self._make_step_result("setup", TaskStatus.SUCCESS, 1.0),
            self._make_step_result("execute", TaskStatus.INCORRECT, 0.0),
            self._make_step_result("verify", TaskStatus.CANCELLED, 0.0),
        ]
        tr = TaskResult(
            task_id="t1", agent_id="a1", sample_id="s1", seed=0,
            status=TaskStatus.SUCCESS,
            step_results=step_results,
        )
        outcome = MockOutcome(task_result=tr, trace={})
        renderer.render_trial_finish(outcome)

        captured = capsys.readouterr()
        # Plain text fallback or rich output should contain step info
        output = captured.out
        assert "Step 1/3" in output or "setup" in output
        assert "Step 2/3" in output or "execute" in output

    def test_no_step_results_no_error(self, capsys):
        from snowl.ui.console import ConsoleRenderer
        renderer = ConsoleRenderer(verbose=True)

        tr = TaskResult(
            task_id="t1", agent_id="a1", sample_id="s1", seed=0,
            status=TaskStatus.SUCCESS,
        )
        outcome = MockOutcome(task_result=tr, trace={})
        renderer.render_trial_finish(outcome)

        captured = capsys.readouterr()
        # Should not contain "Step" header when no step_results
        assert "Step 1/" not in captured.out

    def test_step_status_display(self, capsys):
        from snowl.ui.console import ConsoleRenderer
        renderer = ConsoleRenderer(verbose=True)

        step_results = [
            self._make_step_result("setup", TaskStatus.SUCCESS, 1.0),
        ]
        tr = TaskResult(
            task_id="t1", agent_id="a1", sample_id="s1", seed=0,
            status=TaskStatus.SUCCESS,
            step_results=step_results,
        )
        outcome = MockOutcome(task_result=tr, trace={})
        renderer.render_trial_finish(outcome)

        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
