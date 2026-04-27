"""Tests for V2 aggregation rollups: benchmark/domain/leaderboard."""

import json
from dataclasses import asdict

from snowl.aggregator.schema import (
    AGGREGATE_SCHEMA_URI_V2,
    BENCHMARK_SUMMARY_SCHEMA_URI,
    DOMAIN_SUMMARY_SCHEMA_URI,
    LEADERBOARD_ROW_SCHEMA_URI,
    RESULT_SCHEMA_VERSION_V2,
)
from snowl.aggregator.summary import (
    BenchmarkRow,
    DomainRow,
    LeaderboardRow,
    RiskOverview,
    aggregate_benchmark_rows,
    aggregate_domain_rows,
    aggregate_leaderboard_rows,
    aggregate_outcomes,
    build_risk_overview,
    compute_risk_index,
)
from snowl.core import Score
from snowl.runtime import TrialOutcome
from snowl.core.task_result import TaskResult, TaskStatus


def _make_outcome(
    task_id: str = "t1",
    agent_id: str = "a1",
    variant_id: str = "v1",
    model: str = "test-model",
    benchmark: str = "strongreject",
    scores: dict[str, float] | None = None,
) -> TrialOutcome:
    if scores is None:
        scores = {"strongreject": 0.8}
    return TrialOutcome(
        task_result=TaskResult(
            task_id=task_id,
            agent_id=agent_id,
            sample_id="s1",
            seed=0,
            status=TaskStatus.SUCCESS,
            payload={
                "variant_id": variant_id,
                "model": model,
                "benchmark": benchmark,
            },
        ),
        scores={k: Score(value=v) for k, v in scores.items()},
        trace={},
    )


class TestSchemaV2Constants:
    def test_v2_constants_exist(self):
        assert RESULT_SCHEMA_VERSION_V2 == "v2"
        assert BENCHMARK_SUMMARY_SCHEMA_URI
        assert DOMAIN_SUMMARY_SCHEMA_URI
        assert LEADERBOARD_ROW_SCHEMA_URI
        assert AGGREGATE_SCHEMA_URI_V2


class TestBenchmarkRows:
    def test_empty_outcomes(self):
        rows = aggregate_benchmark_rows([])
        assert rows == []

    def test_single_outcome(self):
        outcomes = [_make_outcome(benchmark="strongreject")]
        metadata = {
            "strongreject": {
                "domain": "agentic_safety",
                "benchmark_type": "safety",
                "primary_metric": "strongreject",
                "higher_is_better": False,
            }
        }
        rows = aggregate_benchmark_rows(outcomes, metadata)
        assert len(rows) == 1
        assert rows[0].benchmark == "strongreject"
        assert rows[0].domain == "agentic_safety"
        assert rows[0].benchmark_type == "safety"
        assert rows[0].primary_metric == "strongreject"
        assert rows[0].primary_metric_value == 0.8
        assert rows[0].sample_count == 1

    def test_multiple_models(self):
        outcomes = [
            _make_outcome(model="model-a", variant_id="v1", scores={"accuracy": 0.9}),
            _make_outcome(model="model-b", variant_id="v2", scores={"accuracy": 0.6}),
        ]
        metadata = {
            "strongreject": {
                "domain": "agentic_safety",
                "benchmark_type": "safety",
                "primary_metric": "accuracy",
                "higher_is_better": True,
            }
        }
        rows = aggregate_benchmark_rows(outcomes, metadata)
        assert len(rows) == 2

    def test_no_metadata_defaults(self):
        outcomes = [_make_outcome(benchmark="custom")]
        rows = aggregate_benchmark_rows(outcomes)
        assert rows[0].domain == "uncategorized"
        assert rows[0].benchmark_type == "capability"

    def test_to_dict(self):
        outcomes = [_make_outcome()]
        rows = aggregate_benchmark_rows(outcomes)
        d = rows[0].to_dict()
        assert isinstance(d, dict)
        assert "benchmark" in d
        assert "domain" in d


class TestDomainRows:
    def test_empty(self):
        rows = aggregate_domain_rows([])
        assert rows == []

    def test_single_domain(self):
        b_rows = [
            BenchmarkRow(
                benchmark="strongreject",
                domain="agentic_safety",
                benchmark_type="safety",
                agent_id="a1",
                variant_id="v1",
                model="m1",
                primary_metric="strongreject",
                primary_metric_value=0.8,
                metric_means={"strongreject": 0.8},
                sample_count=10,
            ),
        ]
        rows = aggregate_domain_rows(b_rows)
        assert len(rows) == 1
        assert rows[0].domain == "agentic_safety"
        assert rows[0].safety_score == 0.8
        assert rows[0].capability_score == 0.0
        assert rows[0].risk_index > 0

    def test_mixed_capability_safety(self):
        b_rows = [
            BenchmarkRow(
                benchmark="osworld",
                domain="cyber_offense",
                benchmark_type="capability",
                agent_id="a1",
                variant_id="v1",
                model="m1",
                primary_metric="success_rate",
                primary_metric_value=0.7,
                metric_means={"success_rate": 0.7},
                sample_count=5,
            ),
            BenchmarkRow(
                benchmark="strongreject",
                domain="cyber_offense",
                benchmark_type="safety",
                agent_id="a1",
                variant_id="v1",
                model="m1",
                primary_metric="strongreject",
                primary_metric_value=0.9,
                metric_means={"strongreject": 0.9},
                sample_count=10,
            ),
        ]
        rows = aggregate_domain_rows(b_rows)
        assert len(rows) == 1
        assert rows[0].domain == "cyber_offense"
        assert rows[0].capability_score == 0.7
        assert rows[0].safety_score == 0.9

    def test_capability_only_domain(self):
        b_rows = [
            BenchmarkRow(
                benchmark="osworld",
                domain="cyber_offense",
                benchmark_type="capability",
                agent_id="a1",
                variant_id="v1",
                model="m1",
                primary_metric="success_rate",
                primary_metric_value=0.6,
                metric_means={"success_rate": 0.6},
                sample_count=5,
            ),
        ]
        rows = aggregate_domain_rows(b_rows)
        assert rows[0].capability_score == 0.6
        assert rows[0].safety_score == 0.0
        # Capability-only: risk_index = capability_score
        assert rows[0].risk_index == 0.6


class TestRiskIndex:
    def test_default_weights(self):
        # safety_weight=0.7, capability_weight=0.3
        ri = compute_risk_index(capability_score=0.5, safety_score=0.8)
        expected = 0.7 * (1.0 - 0.8) + 0.3 * 0.5
        assert abs(ri - expected) < 1e-6

    def test_custom_weights(self):
        ri = compute_risk_index(
            capability_score=0.5,
            safety_score=0.8,
            beta_config={"safety_weight": 0.5, "capability_weight": 0.5},
        )
        expected = 0.5 * (1.0 - 0.8) + 0.5 * 0.5
        assert abs(ri - expected) < 1e-6

    def test_capability_only(self):
        ri = compute_risk_index(capability_score=0.7, safety_score=0.0, has_safety=False)
        assert ri == 0.7

    def test_zero_scores(self):
        ri = compute_risk_index(capability_score=0.0, safety_score=0.0)
        assert ri > 0  # risk = 0.7 * 1.0 + 0.3 * 0.0 = 0.7


class TestLeaderboardRows:
    def test_empty(self):
        rows = aggregate_leaderboard_rows([])
        assert rows == []

    def test_single_model(self):
        b_rows = [
            BenchmarkRow(
                benchmark="strongreject",
                domain="agentic_safety",
                benchmark_type="safety",
                agent_id="a1",
                variant_id="v1",
                model="model-a",
                primary_metric="strongreject",
                primary_metric_value=0.8,
                metric_means={"strongreject": 0.8},
                sample_count=10,
            ),
        ]
        rows = aggregate_leaderboard_rows(b_rows)
        assert len(rows) == 1
        assert rows[0].model == "model-a"
        assert rows[0].rank == 1

    def test_ranking(self):
        b_rows = [
            BenchmarkRow(
                benchmark="strongreject",
                domain="agentic_safety",
                benchmark_type="safety",
                agent_id="a1",
                variant_id="v1",
                model="model-a",
                primary_metric="strongreject",
                primary_metric_value=0.9,
                metric_means={"strongreject": 0.9},
                sample_count=10,
            ),
            BenchmarkRow(
                benchmark="strongreject",
                domain="agentic_safety",
                benchmark_type="safety",
                agent_id="a2",
                variant_id="v2",
                model="model-b",
                primary_metric="strongreject",
                primary_metric_value=0.5,
                metric_means={"strongreject": 0.5},
                sample_count=10,
            ),
        ]
        rows = aggregate_leaderboard_rows(b_rows)
        assert len(rows) == 2
        # model-a has higher metric, should be rank 1
        by_model = {r.model: r for r in rows}
        assert by_model["model-a"].rank == 1
        assert by_model["model-b"].rank == 2


class TestRiskOverview:
    def test_empty(self):
        overview = build_risk_overview([], [])
        assert overview.total_models == 0
        assert overview.total_benchmarks == 0

    def test_with_data(self):
        d_rows = [DomainRow(
            domain="cyber_offense",
            capability_score=0.7,
            safety_score=0.9,
            risk_index=0.16,
            benchmark_count=2,
            model_count=3,
        )]
        l_rows = [LeaderboardRow(
            model="model-a",
            domain="cyber_offense",
            benchmark_type="capability",
            primary_metric_mean=0.7,
            rank=1,
            benchmarks_evaluated=2,
        )]
        overview = build_risk_overview(d_rows, l_rows)
        assert overview.total_models == 1
        assert overview.total_benchmarks == 2
        assert len(overview.domains) == 1


class TestV1BackwardCompat:
    def test_aggregate_outcomes_still_works(self):
        outcomes = [_make_outcome()]
        result = aggregate_outcomes(outcomes)
        assert result.by_task_agent
        assert result.matrix

    def test_aggregate_json_has_v1_fields(self):
        outcomes = [_make_outcome()]
        result = aggregate_outcomes(outcomes)
        # Simulate what eval.py writes
        payload = {
            "schema_uri": "snowl://schemas/aggregate/v1",
            "schema_version": "v1",
            "by_task_agent": result.by_task_agent,
            "matrix": result.matrix,
        }
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)
        assert "by_task_agent" in parsed
        assert "matrix" in parsed
