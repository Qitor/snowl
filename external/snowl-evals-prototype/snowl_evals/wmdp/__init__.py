"""snowl-evals wmdp benchmark adapter."""
from __future__ import annotations


def register_cyber(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    registry.register(
        name="wmdp-cyber",
        info=BenchmarkInfo(
            name="wmdp-cyber",
            description="WMDP-Cyber benchmark adapter.",
            display_name="WMDP Cyber",
            short_description="WMDP cyber multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="wmdp",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.wmdp.adapter", "WMDPBenchmarkAdapter"),
    )


def register_chem(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CBRN_HAZARDOUS = RiskDomain(
        domain_id="cbrn_hazardous",
        display_name="CBRN Hazardous",
        description="Capability to assist with chemical, biological, radiological, or nuclear hazards.",
    )

    registry.register(
        name="wmdp-chem",
        info=BenchmarkInfo(
            name="wmdp-chem",
            description="WMDP-Chem benchmark adapter.",
            display_name="WMDP Chem",
            short_description="WMDP chemistry multiple-choice benchmark",
            domain="chemical_risks",
            benchmark_type="capability",
            family="wmdp",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "chemistry"],
            risk_domains=(RISK_CBRN_HAZARDOUS,),
        ),
        factory=_lazy_factory("snowl_evals.wmdp.adapter", "WMDPBenchmarkAdapter", variant="wmdp-chem"),
    )


def register(registry) -> None:
    register_cyber(registry)
    register_chem(registry)
