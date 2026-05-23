"""snowl-evals mask benchmark adapter."""
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
        name="mask",
        info=BenchmarkInfo(
            name="mask",
            description="MASK benchmark adapter.",
            display_name="MASK",
            short_description="Model Alignment between Sycophancy and Knowledge",
            domain="agentic_safety",
            benchmark_type="safety",
            family="mask",
            primary_metric="mask_score",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["situational_awareness", "deception"],
            risk_domains=(RISK_UNSAFE_COMPLIANCE,),
        ),
        factory=_lazy_factory("snowl_evals.mask.adapter", "MASKBenchmarkAdapter"),
    )
