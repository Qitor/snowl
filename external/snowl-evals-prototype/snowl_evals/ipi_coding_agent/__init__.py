"""snowl-evals ipi_coding_agent benchmark adapter."""
from __future__ import annotations


def register(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_PROMPT_INJECTION = RiskDomain(
        domain_id="prompt_injection",
        display_name="Prompt Injection",
        description="Resistance to adversarial prompt injection attacks in agentic settings.",
    )

    registry.register(
        name="ipi_coding_agent",
        info=BenchmarkInfo(
            name="ipi_coding_agent",
            description="Coding-agent prompt-injection benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="ipi_coding_agent",
            primary_metric="ipi_coding_agent_score",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["prompt_injection", "coding", "tool_use"],
            risk_domains=(RISK_PROMPT_INJECTION,),
        ),
        factory=_lazy_factory("snowl_evals.ipi_coding_agent.adapter", "IPICodingAgentBenchmarkAdapter"),
    )
