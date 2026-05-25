"""Tests for metric definition factory functions and bootstrap CI."""

import math
import pytest

from snowl.aggregator.metrics import MetricDefinition
from snowl.aggregator.metric_defs import (
    accuracy,
    at_least,
    bootstrap_stderr,
    compute_bootstrap_stderr,
    grouped,
    max_score,
    mean_score,
    median_score,
    pass_at_k_metric,
    stderr,
)


class TestAccuracy:
    def test_returns_metric_definition(self):
        m = accuracy()
        assert isinstance(m, MetricDefinition)
        assert m.name == "accuracy"
        assert m.aggregation == "mean"
        assert m.higher_is_better is True


class TestMeanScore:
    def test_returns_metric_definition(self):
        m = mean_score()
        assert m.name == "mean_score"
        assert m.aggregation == "mean"


class TestStderr:
    def test_returns_metric_definition(self):
        m = stderr()
        assert m.name == "stderr"
        assert m.higher_is_better is False


class TestMaxScore:
    def test_returns_metric_definition(self):
        m = max_score()
        assert m.name == "max_score"
        assert m.aggregation == "max"


class TestMedianScore:
    def test_returns_metric_definition(self):
        m = median_score()
        assert m.name == "median_score"
        assert m.aggregation == "median"


class TestAtLeast:
    def test_threshold_in_name(self):
        m = at_least(0.8)
        assert "0.8" in m.name
        assert m.aggregation == "mean"


class TestPassAtKMetric:
    def test_k_in_name(self):
        m = pass_at_k_metric(k=5)
        assert "5" in m.name
        assert m.higher_is_better is True


class TestGrouped:
    def test_key_in_name(self):
        m = grouped("domain")
        assert "domain" in m.name

    def test_with_inner(self):
        inner = max_score()
        m = grouped("task_id", inner=inner)
        assert m.aggregation == "max"


class TestBootstrapStderr:
    def test_returns_metric_definition(self):
        m = bootstrap_stderr(n_resamples=500)
        assert m.name == "bootstrap_stderr"
        assert m.higher_is_better is False


class TestComputeBootstrapStderr:
    def test_small_sample(self):
        values = [1.0, 0.0, 1.0, 0.0, 1.0]
        se = compute_bootstrap_stderr(values, n_resamples=1000, seed=42)
        assert se > 0.0
        # Should be in a reasonable range
        assert se < 1.0

    def test_single_value(self):
        se = compute_bootstrap_stderr([0.5])
        assert se == 0.0

    def test_empty(self):
        se = compute_bootstrap_stderr([])
        assert se == 0.0

    def test_deterministic_with_seed(self):
        values = [1.0, 0.0, 1.0, 0.0, 1.0]
        se1 = compute_bootstrap_stderr(values, n_resamples=500, seed=123)
        se2 = compute_bootstrap_stderr(values, n_resamples=500, seed=123)
        assert se1 == se2

    def test_all_same(self):
        se = compute_bootstrap_stderr([1.0, 1.0, 1.0], n_resamples=100, seed=1)
        assert se == 0.0
