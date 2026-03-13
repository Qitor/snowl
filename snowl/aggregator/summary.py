"""Aggregation contracts for compare outputs and monitor-facing metric matrices.

Framework role:
- Converts per-trial `TrialOutcome` rows into two stable projections consumed by reports/UI.
- Defines grouping semantics by `(task_id, agent_id, variant_id)` and mean-based metric rollups.

Runtime/usage wiring:
- `aggregate_outcomes` is called from `snowl.eval` after execution/scoring; its output is written into aggregate artifacts.
- Key formats produced here (`task::agent(::variant)` and `agent#variant`) are consumed by compare rendering and downstream tooling.

Change guardrails:
- Treat key-shape or rollup-policy changes as contract changes; update tests/docs together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.runtime import TrialOutcome


@dataclass(frozen=True)
class AggregateResult:
    by_task_agent: dict[str, dict[str, Any]]
    matrix: dict[str, dict[str, dict[str, float]]]


def _mean(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)


def aggregate_outcomes(outcomes: list[TrialOutcome]) -> AggregateResult:
    """Aggregate multi-metric scores by task and agent."""

    groups: dict[tuple[str, str, str], list[TrialOutcome]] = {}
    for o in outcomes:
        variant_id = str((o.task_result.payload or {}).get("variant_id") or "default")
        key = (o.task_result.task_id, o.task_result.agent_id, variant_id)
        groups.setdefault(key, []).append(o)

    by_task_agent: dict[str, dict[str, Any]] = {}
    matrix: dict[str, dict[str, dict[str, float]]] = {}

    for (task_id, agent_id, variant_id), bucket in sorted(groups.items(), key=lambda x: x[0]):
        metric_values: dict[str, list[float]] = {}
        statuses: dict[str, int] = {}
        for out in bucket:
            statuses[out.task_result.status.value] = statuses.get(out.task_result.status.value, 0) + 1
            for metric, score in out.scores.items():
                metric_values.setdefault(metric, []).append(float(score.value))

        metric_means = {metric: _mean(vals) for metric, vals in metric_values.items()}

        group_key = (
            f"{task_id}::{agent_id}"
            if variant_id == "default"
            else f"{task_id}::{agent_id}::{variant_id}"
        )
        by_task_agent[group_key] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "variant_id": variant_id,
            "model": (bucket[0].task_result.payload or {}).get("model"),
            "count": len(bucket),
            "status_counts": statuses,
            "metrics": metric_means,
        }
        label = agent_id if variant_id == "default" else f"{agent_id}#{variant_id}"
        matrix.setdefault(task_id, {})[label] = metric_means

    return AggregateResult(by_task_agent=by_task_agent, matrix=matrix)
