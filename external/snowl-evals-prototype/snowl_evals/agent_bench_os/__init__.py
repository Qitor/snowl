"""snowl-evals agent_bench_os benchmark adapter."""
from __future__ import annotations


def register(registry) -> None:
    from snowl.benchmarks.base import BenchmarkInfo
    from snowl.benchmarks.registry import _lazy_factory

    registry.register(
        name="agent_bench_os",
        info=BenchmarkInfo(
            name="agent_bench_os",
            description="AgentBench OS benchmark adapter.",
            domain="agentic_capability",
            benchmark_type="capability",
            family="agent_bench",
            primary_metric="agent_bench_os_success",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["terminal", "tool_use", "os"],
            risk_domains=(),
        ),
        factory=_lazy_factory("snowl_evals.agent_bench_os.adapter", "AgentBenchOSBenchmarkAdapter"),
    )
