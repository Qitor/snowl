"""snowl-evals agentharm benchmark adapter."""
from __future__ import annotations


def register_harm(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_HARMFUL_TOOL_USE = RiskDomain(
        domain_id="harmful_tool_use",
        display_name="Harmful Tool Use",
        description="Propensity to use tools in ways that cause real-world harm.",
    )

    registry.register(
        name="agentharm",
        info=BenchmarkInfo(
            name="agentharm",
            description="AgentHarm benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentharm",
            primary_metric="agentharm_safety",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["agent_safety", "tool_use", "refusal"],
            risk_domains=(RISK_HARMFUL_TOOL_USE,),
        ),
        factory=_lazy_factory("snowl_evals.agentharm.adapter", "AgentHarmBenchmarkAdapter"),
    )


def register_benign(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_HARMFUL_TOOL_USE = RiskDomain(
        domain_id="harmful_tool_use",
        display_name="Harmful Tool Use",
        description="Propensity to use tools in ways that cause real-world harm.",
    )

    registry.register(
        name="agentharm_benign",
        info=BenchmarkInfo(
            name="agentharm_benign",
            description="AgentHarm benign benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentharm",
            primary_metric="agentharm_safety",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["agent_safety", "tool_use", "refusal"],
            risk_domains=(RISK_HARMFUL_TOOL_USE,),
        ),
        factory=_lazy_factory("snowl_evals.agentharm.adapter", "AgentHarmBenchmarkAdapter", mode="benign"),
    )


def register(registry) -> None:
    register_harm(registry)
    register_benign(registry)
