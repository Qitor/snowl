"""snowl-evals bfcl benchmark adapter."""
from __future__ import annotations


def register(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo
    from snowl.benchmarks.registry import _lazy_factory

    registry.register(
        name="bfcl",
        info=BenchmarkInfo(
            name="bfcl",
            description="Function-calling benchmark adapter.",
            domain="agentic_capability",
            benchmark_type="capability",
            family="bfcl",
            primary_metric="function_call_accuracy",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["function_calling", "tool_use"],
            risk_domains=(),
        ),
        factory=_lazy_factory("snowl_evals.bfcl.adapter", "BFCLBenchmarkAdapter"),
    )
