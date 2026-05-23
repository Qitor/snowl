"""Tests for aggregate_risk_domain_rows and RiskDomainRow."""

from __future__ import annotations

from snowl.aggregator.summary import (
    BenchmarkRow,
    aggregate_risk_domain_rows,
    compute_risk_index,
)
from snowl.benchmarks.base import RiskDomain


def _make_benchmark_row(
    *,
    benchmark: str,
    benchmark_type: str,
    primary_metric_value: float,
    domain: str = "agentic_safety",
) -> BenchmarkRow:
    return BenchmarkRow(
        benchmark=benchmark,
        domain=domain,
        benchmark_type=benchmark_type,
        agent_id="test-agent",
        variant_id="default",
        model="test-model",
        primary_metric="score",
        primary_metric_value=primary_metric_value,
        metric_means={"score": primary_metric_value},
        sample_count=10,
    )


def test_aggregate_risk_domain_rows_groups_by_domain() -> None:
    rd_pi = RiskDomain(domain_id="prompt_injection", display_name="Prompt Injection")
    rd_ht = RiskDomain(domain_id="harmful_tool_use", display_name="Harmful Tool Use")
    risk_domain_map = {
        "agentdojo": (rd_pi,),
        "agentharm": (rd_ht,),
        "toolemu": (rd_ht, rd_pi),
    }
    rows = [
        _make_benchmark_row(benchmark="agentdojo", benchmark_type="safety", primary_metric_value=0.8),
        _make_benchmark_row(benchmark="agentharm", benchmark_type="safety", primary_metric_value=0.6),
        _make_benchmark_row(benchmark="toolemu", benchmark_type="safety", primary_metric_value=0.5),
    ]
    result = aggregate_risk_domain_rows(rows, risk_domain_map=risk_domain_map)
    assert len(result) == 2
    pi_row = next(r for r in result if r.risk_domain_id == "prompt_injection")
    ht_row = next(r for r in result if r.risk_domain_id == "harmful_tool_use")
    assert pi_row.display_name == "Prompt Injection"
    assert ht_row.display_name == "Harmful Tool Use"
    # agentdojo (0.8) and toolemu (0.5) → mean safety = 0.65
    assert pi_row.safety_score == round((0.8 + 0.5) / 2, 4)
    assert pi_row.benchmark_count == 2
    # agentharm (0.6) and toolemu (0.5) → mean safety = 0.55
    assert ht_row.safety_score == round((0.6 + 0.5) / 2, 4)
    assert ht_row.benchmark_count == 2


def test_aggregate_risk_domain_rows_mixed_types() -> None:
    rd_cyber = RiskDomain(domain_id="cyber_capability", display_name="Cyber")
    risk_domain_map = {
        "wmdp-cyber": (rd_cyber,),
    }
    rows = [
        _make_benchmark_row(benchmark="wmdp-cyber", benchmark_type="capability", primary_metric_value=0.7),
    ]
    result = aggregate_risk_domain_rows(rows, risk_domain_map=risk_domain_map)
    assert len(result) == 1
    assert result[0].capability_score == 0.7
    assert result[0].safety_score == 0.0
    # No safety data → risk_index = capability_score
    assert result[0].risk_index == 0.7


def test_aggregate_risk_domain_rows_empty() -> None:
    result = aggregate_risk_domain_rows([])
    assert result == []


def test_aggregate_risk_domain_rows_no_risk_domains() -> None:
    """Benchmarks without risk domains should not appear in output."""
    rows = [
        _make_benchmark_row(benchmark="unknown_bench", benchmark_type="capability", primary_metric_value=0.5),
    ]
    result = aggregate_risk_domain_rows(rows, risk_domain_map={})
    assert result == []


def test_compute_risk_index_with_safety() -> None:
    ri = compute_risk_index(capability_score=0.5, safety_score=0.8, has_safety=True)
    # 0.7 * (1 - 0.8) + 0.3 * 0.5 = 0.14 + 0.15 = 0.29
    assert abs(ri - 0.29) < 1e-6


def test_compute_risk_index_without_safety() -> None:
    ri = compute_risk_index(capability_score=0.6, safety_score=0.0, has_safety=False)
    assert ri == 0.6


def test_compute_risk_index_custom_weights() -> None:
    ri = compute_risk_index(
        capability_score=0.5,
        safety_score=0.8,
        has_safety=True,
        beta_config={"safety_weight": 0.5, "capability_weight": 0.5},
    )
    # 0.5 * (1 - 0.8) + 0.5 * 0.5 = 0.1 + 0.25 = 0.35
    assert abs(ri - 0.35) < 1e-6


def test_risk_domain_row_to_dict() -> None:
    from snowl.aggregator.summary import RiskDomainRow
    row = RiskDomainRow(
        risk_domain_id="test",
        display_name="Test",
        capability_score=0.5,
        safety_score=0.8,
        risk_index=0.29,
        benchmark_count=3,
    )
    d = row.to_dict()
    assert d["risk_domain_id"] == "test"
    assert d["benchmark_count"] == 3
