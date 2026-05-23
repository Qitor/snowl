"""snowl-evals fortress benchmark adapter."""
from __future__ import annotations


def register_adversarial(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_OVER_REFUSAL = RiskDomain(
        domain_id="over_refusal",
        display_name="Over-Refusal",
        description="Tendency to refuse benign requests that appear marginally sensitive.",
    )
    RISK_UNSAFE_COMPLIANCE = RiskDomain(
        domain_id="unsafe_compliance",
        display_name="Unsafe Compliance",
        description="Willingness to comply with explicitly harmful instructions.",
    )

    registry.register(
        name="fortress_adversarial",
        info=BenchmarkInfo(
            name="fortress_adversarial",
            description="FORTRESS adversarial benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="fortress",
            primary_metric="ARS",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["safeguards", "refusal"],
            risk_domains=(RISK_OVER_REFUSAL, RISK_UNSAFE_COMPLIANCE),
        ),
        factory=_lazy_factory("snowl_evals.fortress.adapter", "FortressBenchmarkAdapter", mode="adversarial"),
    )


def register_benign(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_OVER_REFUSAL = RiskDomain(
        domain_id="over_refusal",
        display_name="Over-Refusal",
        description="Tendency to refuse benign requests that appear marginally sensitive.",
    )

    registry.register(
        name="fortress_benign",
        info=BenchmarkInfo(
            name="fortress_benign",
            description="FORTRESS benign benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="fortress",
            primary_metric="ORS",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["safeguards", "refusal"],
            risk_domains=(RISK_OVER_REFUSAL,),
        ),
        factory=_lazy_factory("snowl_evals.fortress.adapter", "FortressBenchmarkAdapter", mode="benign"),
    )


def register(registry) -> None:
    register_adversarial(registry)
    register_benign(registry)
