"""Tests verifying that built-in benchmarks have appropriate risk_domains metadata."""

from __future__ import annotations

import pytest

from snowl.benchmarks.registry import get_default_benchmark_registry


# Benchmarks that are pure capability tests — no safety risk domains expected
PURE_CAPABILITY_BENCHMARKS = {"agent_bench_os", "bfcl"}

# Generic adapters — no risk domains expected
GENERIC_ADAPTERS = {"jsonl", "csv"}

# Safety benchmarks that MUST have at least one risk domain
SAFETY_BENCHMARKS_WITH_RISK_DOMAINS = {
    "agentdojo",
    "agentharm",
    "agentharm_benign",
    "toolemu",
    "xstest",
    "fortress_adversarial",
    "fortress_benign",
    "strongreject",
    "ipi_coding_agent",
    "coconot",
    "agentsafetybench",
    "mask",
}


def test_safety_benchmarks_have_risk_domains() -> None:
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        name = entry.info.name
        if name in SAFETY_BENCHMARKS_WITH_RISK_DOMAINS:
            assert entry.info.risk_domains, (
                f"Safety benchmark '{name}' should have at least one risk domain"
            )


def test_capability_benchmarks_may_have_risk_domains() -> None:
    """Capability benchmarks may have risk domains if they measure frontier capabilities."""
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        name = entry.info.name
        if name in PURE_CAPABILITY_BENCHMARKS | GENERIC_ADAPTERS:
            # These should NOT have risk domains
            assert entry.info.risk_domains == (), (
                f"Pure capability benchmark '{name}' should not have risk domains"
            )


def test_cyber_benchmarks_have_cyber_capability_domain() -> None:
    """Benchmarks in cyber_offense domain with MCQ-style tasks should have cyber_capability risk domain."""
    # terminalbench and osworld are cyber_offense but agent-based, not MCQ cyber-knowledge
    agent_based_cyber = {"terminalbench", "osworld"}
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        if entry.info.domain == "cyber_offense" and entry.info.benchmark_type == "capability":
            if entry.info.name in agent_based_cyber:
                continue
            domain_ids = [rd.domain_id for rd in entry.info.risk_domains]
            assert "cyber_capability" in domain_ids, (
                f"cyber_offense capability benchmark '{entry.info.name}' should have cyber_capability risk domain"
            )


def test_risk_domains_are_not_none() -> None:
    """All registered benchmarks must have risk_domains as a tuple, never None."""
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        assert entry.info.risk_domains is not None, (
            f"Benchmark '{entry.info.name}' has risk_domains=None"
        )


def test_wmdp_chem_has_cbrn_domain() -> None:
    registry = get_default_benchmark_registry()
    # Get info from registry listing, not from created adapter
    for entry in registry.list():
        if entry.info.name == "wmdp-chem":
            domain_ids = [rd.domain_id for rd in entry.info.risk_domains]
            assert "cbrn_hazardous" in domain_ids
            return
    pytest.fail("wmdp-chem not found in registry")


def test_terminalbench_and_osworld_have_long_horizon_domain() -> None:
    registry = get_default_benchmark_registry()
    for entry in registry.list():
        if entry.info.name in ("terminalbench", "osworld"):
            domain_ids = [rd.domain_id for rd in entry.info.risk_domains]
            assert "long_horizon" in domain_ids, (
                f"'{entry.info.name}' should have long_horizon risk domain"
            )
