"""Metric aggregation with per-metric strategy, stderr, and definition metadata.

Framework role:
- Defines ``MetricDefinition`` (aggregation strategy, direction, description) and
  ``MetricReport`` (value + stderr + sample count) for structured metric output.
- Provides ``MetricAggregator`` which computes aggregates respecting per-metric
  strategies (mean, max, min, median) and produces reports with stderr.

Runtime/usage wiring:
- Called from ``summary.py`` aggregation functions to produce richer per-metric data.
- Consumed by the report layer for color-coding and threshold display.

Change guardrails:
- MetricDefinition and MetricReport are data contracts; changes affect report/artifact output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING


@dataclass(frozen=True)
class MetricDefinition:
    """Declaration of how a named metric should be aggregated and interpreted."""

    name: str
    aggregation: str = "mean"  # "mean" | "max" | "min" | "median"
    higher_is_better: bool = True
    description: str = ""


@dataclass(frozen=True)
class MetricReport:
    """Aggregated metric result with statistical context."""

    name: str
    value: float
    stderr: float
    sample_count: int
    higher_is_better: bool
    definition: MetricDefinition

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "stderr": self.stderr,
            "sample_count": self.sample_count,
            "higher_is_better": self.higher_is_better,
            "aggregation": self.definition.aggregation,
            "description": self.definition.description,
        }


# ---------------------------------------------------------------------------
# Aggregation functions
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _max(values: list[float]) -> float:
    return 0.0 if not values else max(values)


def _min(values: list[float]) -> float:
    return 0.0 if not values else min(values)


def _stderr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance / n)


_AGGREGATION_FN: dict[str, Callable[[list[float]], float]] = {
    "mean": _mean,
    "median": _median,
    "max": _max,
    "min": _min,
}


# ---------------------------------------------------------------------------
# MetricAggregator
# ---------------------------------------------------------------------------

class MetricAggregator:
    """Compute per-metric aggregates respecting individual aggregation strategies."""

    def aggregate(
        self,
        scores: list[dict[str, float]],
        definitions: list[MetricDefinition] | None = None,
    ) -> list[MetricReport]:
        """Aggregate a list of score maps into per-metric reports.

        Args:
            scores: List of {metric_name: value} dicts (one per trial/sample).
            definitions: Optional per-metric definitions. If a metric has no
                explicit definition, a default (mean, higher_is_better=True) is used.

        Returns:
            List of MetricReport, one per distinct metric name found in *scores*.
        """
        if not scores:
            return []

        def_map: dict[str, MetricDefinition] = {}
        if definitions:
            for d in definitions:
                def_map[d.name] = d

        # Collect values per metric
        metric_values: dict[str, list[float]] = {}
        for score_map in scores:
            for name, value in score_map.items():
                metric_values.setdefault(name, []).append(float(value))

        reports: list[MetricReport] = []
        for name in sorted(metric_values):
            values = metric_values[name]
            defn = def_map.get(name, MetricDefinition(name=name))
            agg_fn = _AGGREGATION_FN.get(defn.aggregation, _mean)
            reports.append(MetricReport(
                name=name,
                value=agg_fn(values),
                stderr=_stderr(values),
                sample_count=len(values),
                higher_is_better=defn.higher_is_better,
                definition=defn,
            ))

        return reports

    def grouped(
        self,
        scores_by_group: dict[str, list[dict[str, float]]],
        definitions: list[MetricDefinition] | None = None,
    ) -> dict[str, list[MetricReport]]:
        """Aggregate scores grouped by a key (e.g. task_id, agent_id, domain).

        Args:
            scores_by_group: Mapping of group label to list of score maps.
            definitions: Optional per-metric definitions.

        Returns:
            Mapping of group label to list of MetricReport.
        """
        result: dict[str, list[MetricReport]] = {}
        for group_key in sorted(scores_by_group):
            result[group_key] = self.aggregate(scores_by_group[group_key], definitions)
        return result

    def metric_means_dict(self, reports: list[MetricReport]) -> dict[str, float]:
        """Convenience: collapse reports into a {name: value} dict (for backward compat)."""
        return {r.name: r.value for r in reports}

    def aggregate_with_scorer_metrics(
        self,
        scores: list[dict[str, float]],
        scorer: Any,
    ) -> list[MetricReport]:
        """Aggregate scores using metric definitions bound to a scorer.

        If the scorer was declared with ``@scorer(metrics=[accuracy(), stderr()])``,
        those MetricDefinitions are used instead of defaults.

        Args:
            scores: List of {metric_name: value} dicts (one per trial/sample).
            scorer: A scorer object that may have ``_metrics`` bound.

        Returns:
            List of MetricReport, one per distinct metric name found in *scores*.
        """
        definitions: list[MetricDefinition] | None = None
        bound = getattr(scorer, "_metrics", None)
        if bound:
            definitions = list(bound)
        return self.aggregate(scores, definitions=definitions)
