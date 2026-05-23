"""Tests for RiskDomain dataclass and BenchmarkInfo.risk_domains default."""

from __future__ import annotations

from snowl.benchmarks.base import BenchmarkInfo, RiskDomain


def test_risk_domain_defaults() -> None:
    rd = RiskDomain(domain_id="test", display_name="Test Domain")
    assert rd.domain_id == "test"
    assert rd.display_name == "Test Domain"
    assert rd.description == ""
    assert rd.severity_levels == ("low", "medium", "high", "critical")
    assert rd.categories == ()


def test_risk_domain_custom() -> None:
    rd = RiskDomain(
        domain_id="cbrn",
        display_name="CBRN",
        description="Chemical/biological/radiological/nuclear hazards",
        severity_levels=("low", "medium", "high"),
        categories=("chem", "bio"),
    )
    assert rd.description == "Chemical/biological/radiological/nuclear hazards"
    assert rd.severity_levels == ("low", "medium", "high")
    assert rd.categories == ("chem", "bio")


def test_risk_domain_frozen() -> None:
    rd = RiskDomain(domain_id="x", display_name="X")
    try:
        rd.domain_id = "y"  # type: ignore[misc]
        assert False, "Should be frozen"
    except AttributeError:
        pass


def test_benchmark_info_risk_domains_default_empty() -> None:
    info = BenchmarkInfo(name="test", description="Test")
    assert info.risk_domains == ()


def test_benchmark_info_with_risk_domains() -> None:
    rd = RiskDomain(domain_id="prompt_injection", display_name="Prompt Injection")
    info = BenchmarkInfo(name="test", description="Test", risk_domains=(rd,))
    assert len(info.risk_domains) == 1
    assert info.risk_domains[0].domain_id == "prompt_injection"


def test_benchmark_info_frozen() -> None:
    info = BenchmarkInfo(name="test", description="Test", risk_domains=())
    try:
        info.risk_domains = ()  # type: ignore[misc]
        assert False, "Should be frozen"
    except AttributeError:
        pass
