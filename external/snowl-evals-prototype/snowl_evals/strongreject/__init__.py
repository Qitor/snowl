"""snowl-evals strongreject benchmark adapter."""
from __future__ import annotations


def register(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_UNSAFE_COMPLIANCE = RiskDomain(
        domain_id="unsafe_compliance",
        display_name="Unsafe Compliance",
        description="Willingness to comply with explicitly harmful instructions.",
    )

    registry.register(
        name="strongreject",
        info=BenchmarkInfo(
            name="strongreject",
            description="StrongReject benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="strongreject",
            primary_metric="strongreject",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["jailbreak", "refusal"],
            risk_domains=(RISK_UNSAFE_COMPLIANCE,),
        ),
        factory=_lazy_factory("snowl_evals.strongreject.adapter", "StrongRejectBenchmarkAdapter"),
    )
