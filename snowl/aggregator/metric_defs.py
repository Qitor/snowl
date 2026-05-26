"""Pre-built metric definitions for common evaluation scenarios.

Framework role:
- Provides factory functions for standard MetricDefinition instances
  used across benchmarks (accuracy, mean, stderr, bootstrap CI, etc.).
- Includes bootstrap_stderr() for robust confidence intervals on small samples.

Runtime/usage wiring:
- Used with ``@scorer(metrics=[accuracy(), stderr()])`` for declarative binding.
- Used directly with ``MetricAggregator.aggregate(scores, definitions=...)``.

Change guardrails:
- No third-party imports. Uses only stdlib random + math for bootstrap.
"""

from __future__ import annotations

import math
import random
from typing import Any

from snowl.aggregator.metrics import MetricDefinition


# ---------------------------------------------------------------------------
# Basic metric factories
# ---------------------------------------------------------------------------

def accuracy(*, higher_is_better: bool = True, description: str = "") -> MetricDefinition:
    """Accuracy metric: proportion of correct results, aggregated by mean."""
    return MetricDefinition(
        name="accuracy",
        aggregation="mean",
        higher_is_better=higher_is_better,
        description=description or "Proportion of correct results.",
    )


def mean_score(*, higher_is_better: bool = True, description: str = "") -> MetricDefinition:
    """Mean score metric: average of continuous scores."""
    return MetricDefinition(
        name="mean_score",
        aggregation="mean",
        higher_is_better=higher_is_better,
        description=description or "Mean score across samples.",
    )


def stderr(*, description: str = "") -> MetricDefinition:
    """Standard error of the mean metric."""
    return MetricDefinition(
        name="stderr",
        aggregation="mean",
        higher_is_better=False,
        description=description or "Standard error of the mean.",
    )


def max_score(*, higher_is_better: bool = True, description: str = "") -> MetricDefinition:
    """Maximum score metric."""
    return MetricDefinition(
        name="max_score",
        aggregation="max",
        higher_is_better=higher_is_better,
        description=description or "Maximum score across samples.",
    )


def median_score(*, higher_is_better: bool = True, description: str = "") -> MetricDefinition:
    """Median score metric."""
    return MetricDefinition(
        name="median_score",
        aggregation="median",
        higher_is_better=higher_is_better,
        description=description or "Median score across samples.",
    )


def at_least(
    threshold: float,
    *,
    higher_is_better: bool = True,
    description: str = "",
) -> MetricDefinition:
    """Proportion of samples meeting a minimum threshold."""
    return MetricDefinition(
        name=f"at_least_{threshold}",
        aggregation="mean",
        higher_is_better=higher_is_better,
        description=description or f"Proportion of samples with score >= {threshold}.",
    )


def pass_at_k_metric(k: int = 1, *, description: str = "") -> MetricDefinition:
    """pass@k metric for code generation evaluation."""
    return MetricDefinition(
        name=f"pass_at_{k}",
        aggregation="mean",
        higher_is_better=True,
        description=description or f"pass@{k}: probability of at least one correct in {k} attempts.",
    )


def grouped(key: str, *, inner: MetricDefinition | None = None, description: str = "") -> MetricDefinition:
    """Grouped metric: aggregate within subgroups defined by a metadata key."""
    base = inner or accuracy()
    return MetricDefinition(
        name=f"{base.name}_by_{key}",
        aggregation=base.aggregation,
        higher_is_better=base.higher_is_better,
        description=description or f"{base.name} grouped by '{key}'.",
    )


def cost_efficiency(*, higher_is_better: bool = True, description: str = "") -> MetricDefinition:
    """Cost efficiency metric: score per unit cost (USD).

    Measures how much evaluation quality is achieved per dollar spent.
    Useful for fair comparison between models with different pricing.
    """
    return MetricDefinition(
        name="cost_efficiency",
        aggregation="mean",
        higher_is_better=higher_is_better,
        description=description or "Score per unit cost (USD).",
    )


# ---------------------------------------------------------------------------
# Bootstrap stderr
# ---------------------------------------------------------------------------

def bootstrap_stderr(n_resamples: int = 1000, seed: int | None = None) -> MetricDefinition:
    """Bootstrap standard error metric.

    Uses resampling to estimate the standard error of the mean,
    providing more robust CIs for small or non-normal samples.
    """
    return MetricDefinition(
        name="bootstrap_stderr",
        aggregation="mean",
        higher_is_better=False,
        description=f"Bootstrap standard error ({n_resamples} resamples).",
    )


def compute_bootstrap_stderr(
    values: list[float],
    n_resamples: int = 1000,
    seed: int | None = None,
) -> float:
    """Compute bootstrap standard error of the mean.

    Args:
        values: Sample values.
        n_resamples: Number of bootstrap resamples.
        seed: Random seed for reproducibility.

    Returns:
        Bootstrap estimate of the standard error of the mean.
    """
    if len(values) < 2:
        return 0.0

    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []

    for _ in range(n_resamples):
        sample = rng.choices(values, k=n)
        means.append(sum(sample) / n)

    if not means:
        return 0.0

    mean_of_means = sum(means) / len(means)
    variance = sum((m - mean_of_means) ** 2 for m in means) / len(means)
    return math.sqrt(variance)
