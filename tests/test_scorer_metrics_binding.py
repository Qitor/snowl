"""Tests for @scorer(metrics=...) declarative binding and get_scorer_metrics."""

import pytest

from snowl.aggregator.metric_defs import accuracy, stderr
from snowl.aggregator.metrics import MetricAggregator, MetricDefinition
from snowl.core.scorer import Score, get_scorer_metrics, scorer


class TestScorerDecoratorMetrics:
    def test_no_metrics(self):
        @scorer
        class MyScorer:
            scorer_id = "my_scorer"
            def score(self, task_result, trace, context):
                return {"accuracy": Score(value=1.0)}

        s = MyScorer()
        assert get_scorer_metrics(s) == []

    def test_with_metrics(self):
        @scorer(metrics=[accuracy(), stderr()])
        class MyScorer:
            scorer_id = "bound_scorer"
            def score(self, task_result, trace, context):
                return {"accuracy": Score(value=1.0)}

        s = MyScorer()
        metrics = get_scorer_metrics(s)
        assert len(metrics) == 2
        assert metrics[0].name == "accuracy"
        assert metrics[1].name == "stderr"

    def test_metrics_stored_as_list(self):
        m = [accuracy()]
        @scorer(metrics=m)
        class S:
            scorer_id = "s1"
            def score(self, task_result, trace, context):
                return {}

        s = S()
        assert isinstance(get_scorer_metrics(s), list)


class TestGetScorerMetrics:
    def test_object_without_metrics(self):
        class Plain:
            scorer_id = "plain"
        assert get_scorer_metrics(Plain()) == []

    def test_object_with_metrics_attr(self):
        class WithMetrics:
            scorer_id = "wm"
            _metrics = [accuracy()]
        assert len(get_scorer_metrics(WithMetrics())) == 1


class TestMetricAggregatorWithScorerMetrics:
    def test_aggregate_with_bound_metrics(self):
        @scorer(metrics=[accuracy()])
        class MyScorer:
            scorer_id = "my_scorer"
            def score(self, task_result, trace, context):
                return {"accuracy": Score(value=1.0)}

        s = MyScorer()
        agg = MetricAggregator()
        scores = [{"accuracy": 1.0}, {"accuracy": 0.0}, {"accuracy": 1.0}]
        reports = agg.aggregate_with_scorer_metrics(scores, s)
        assert len(reports) == 1
        assert reports[0].name == "accuracy"
        assert abs(reports[0].value - 2 / 3) < 1e-9

    def test_aggregate_without_bound_metrics_uses_defaults(self):
        class PlainScorer:
            scorer_id = "plain"
            def score(self, task_result, trace, context):
                return {"accuracy": Score(value=0.5)}

        s = PlainScorer()
        agg = MetricAggregator()
        scores = [{"accuracy": 0.5}]
        reports = agg.aggregate_with_scorer_metrics(scores, s)
        assert len(reports) == 1
        assert reports[0].name == "accuracy"
