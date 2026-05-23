"""snowl-evals cybermetric benchmark adapter."""
from __future__ import annotations


def _register_one(registry, dataset_name: str) -> None:
    from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
    from snowl.benchmarks.registry import _lazy_factory

    RISK_CYBER_CAPABILITY = RiskDomain(
        domain_id="cyber_capability",
        display_name="Cyber Capability",
        description="Capability to assist with offensive cybersecurity operations.",
    )

    adapter_name = f"cybermetric_{dataset_name.rsplit('-', 1)[-1]}"
    registry.register(
        name=adapter_name,
        info=BenchmarkInfo(
            name=adapter_name,
            description="CyberMetric multiple-choice benchmark adapter.",
            display_name=dataset_name,
            short_description=f"{dataset_name} cybersecurity multiple-choice benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="cybermetric",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["mcq", "cybersecurity"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl_evals.cybermetric.adapter", "CyberMetricBenchmarkAdapter", dataset_name=dataset_name),
    )


def register_80(registry) -> None:
    _register_one(registry, "CyberMetric-80")


def register_500(registry) -> None:
    _register_one(registry, "CyberMetric-500")


def register_2000(registry) -> None:
    _register_one(registry, "CyberMetric-2000")


def register_10000(registry) -> None:
    _register_one(registry, "CyberMetric-10000")


def register(registry) -> None:
    for dataset_name in ("CyberMetric-80", "CyberMetric-500", "CyberMetric-2000", "CyberMetric-10000"):
        _register_one(registry, dataset_name)
