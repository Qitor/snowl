from __future__ import annotations

from snowl.aggregator import aggregate_outcomes
from snowl.core import Score, TaskResult, TaskStatus
from snowl.runtime import TrialOutcome


def _outcome(task: str, agent: str, acc: float, status: TaskStatus) -> TrialOutcome:
    return TrialOutcome(
        task_result=TaskResult(
            task_id=task,
            agent_id=agent,
            sample_id="s1",
            seed=1,
            status=status,
            final_output={},
        ),
        scores={"accuracy": Score(value=acc), "cost": Score(value=0.5)},
        trace={"trace_events": []},
    )


def test_aggregate_outcomes_by_task_agent_and_matrix() -> None:
    outcomes = [
        _outcome("t1", "a1", 1.0, TaskStatus.SUCCESS),
        _outcome("t1", "a1", 0.0, TaskStatus.INCORRECT),
        _outcome("t1", "a2", 1.0, TaskStatus.SUCCESS),
    ]

    agg = aggregate_outcomes(outcomes)
    key = "t1::a1"
    assert key in agg.by_task_agent
    assert agg.by_task_agent[key]["count"] == 2
    assert agg.by_task_agent[key]["status_counts"]["success"] == 1
    assert agg.by_task_agent[key]["status_counts"]["incorrect"] == 1
    assert agg.matrix["t1"]["a2"]["accuracy"] == 1.0
