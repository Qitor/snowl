"""snowl-evals sec_qa benchmark adapter."""
from __future__ import annotations


def register_v1(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    registry.register(
        name="sec_qa_v1",
        info=BenchmarkInfo(
            name="sec_qa_v1",
            description="SecQA v1 multiple-choice benchmark adapter.",
            display_name="SecQA v1",
            short_description="SecQA v1 cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sec_qa",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.sec_qa.adapter", "SecQABenchmarkAdapter", variant="secqa_v1"),
    )


def register_v2(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    registry.register(
        name="sec_qa_v2",
        info=BenchmarkInfo(
            name="sec_qa_v2",
            description="SecQA v2 multiple-choice benchmark adapter.",
            display_name="SecQA v2",
            short_description="SecQA v2 cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sec_qa",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.sec_qa.adapter", "SecQABenchmarkAdapter", variant="secqa_v2"),
    )


def register(registry) -> None:
    register_v1(registry)
    register_v2(registry)
