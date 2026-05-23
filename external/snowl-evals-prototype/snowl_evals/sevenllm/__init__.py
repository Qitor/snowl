"""snowl-evals sevenllm benchmark adapter."""
from __future__ import annotations


def register_mcq_en(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    registry.register(
        name="sevenllm_mcq_en",
        info=BenchmarkInfo(
            name="sevenllm_mcq_en",
            description="SEVENLLM English multiple-choice benchmark adapter.",
            display_name="SEVENLLM MCQ EN",
            short_description="SEVENLLM English cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sevenllm",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity", "en"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.sevenllm.adapter", "SevenLLMMCQBenchmarkAdapter", language="en"),
    )


def register_mcq_zh(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    registry.register(
        name="sevenllm_mcq_zh",
        info=BenchmarkInfo(
            name="sevenllm_mcq_zh",
            description="SEVENLLM Chinese multiple-choice benchmark adapter.",
            display_name="SEVENLLM MCQ ZH",
            short_description="SEVENLLM Chinese cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="sevenllm",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity", "zh"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.sevenllm.adapter", "SevenLLMMCQBenchmarkAdapter", language="zh"),
    )


def register(registry) -> None:
    register_mcq_en(registry)
    register_mcq_zh(registry)
