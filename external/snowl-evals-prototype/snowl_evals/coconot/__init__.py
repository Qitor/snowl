"""snowl-evals coconot benchmark adapter."""
from __future__ import annotations


def register(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_OVER_REFUSAL = RiskDomain(
        domain_id="over_refusal",
        display_name="Over-Refusal",
        description="Tendency to refuse benign requests that appear marginally sensitive.",
    )

    registry.register(
        name="coconot",
        info=BenchmarkInfo(
            name="coconot",
            description="Coconot benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="coconot",
            primary_metric="noncompliance_score",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["noncompliance", "refusal"],
            risk_domains=(RISK_OVER_REFUSAL,),
        ),
        factory=_lazy_factory("snowl_evals.coconot.adapter", "CoconotBenchmarkAdapter"),
    )
