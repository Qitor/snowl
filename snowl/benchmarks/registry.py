"""Benchmark adapter registry and built-in adapter wiring table.

Framework role:
- Maps benchmark names to factories and exposes creation/listing APIs used by CLI and benchmark orchestration.
- Central place for adding/removing built-in benchmark integrations.

Runtime/usage wiring:
- Imported by benchmark command flow to resolve adapters by name.
- Key top-level symbols in this file: `RegisteredBenchmark`, `BenchmarkRegistry`, `get_default_benchmark_registry`, `register_builtin_benchmarks`.

Change guardrails:
- Registration keys are user-facing CLI contract; treat renames/removals as breaking changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkInfo
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.errors import SnowlValidationError


AdapterFactory = Callable[..., BenchmarkAdapter]


def _lazy_factory(module_path: str, class_name: str, **default_kwargs: Any) -> AdapterFactory:
    """Create a lazy factory that defers adapter import until first use.

    This is the recommended registration pattern for plugin-based adapters
    (e.g. snowl-evals benchmarks) to avoid eager imports of heavy dependencies.

    Parameters:
        module_path: Dotted module path (e.g. "snowl_evals.strongreject.adapter").
        class_name: Name of the adapter class in the module.
        **default_kwargs: Keyword arguments forwarded to the adapter constructor.
    """
    def factory(**kwargs: Any) -> BenchmarkAdapter:
        import importlib
        merged = {**default_kwargs, **kwargs}
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(**merged)
    factory.__qualname__ = f"_lazy_factory({module_path}:{class_name})"
    return factory


@dataclass(frozen=True)
class RegisteredBenchmark:
    info: BenchmarkInfo
    factory: AdapterFactory


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegisteredBenchmark] = {}

    def register(self, name: str, info: BenchmarkInfo, factory: AdapterFactory) -> None:
        key = name.strip()
        if not key:
            raise SnowlValidationError("Benchmark name must be non-empty.")
        self._entries[key] = RegisteredBenchmark(info=info, factory=factory)

    def list(self) -> list[RegisteredBenchmark]:
        return [self._entries[k] for k in sorted(self._entries.keys())]

    def create(self, name: str, **kwargs: Any) -> BenchmarkAdapter:
        entry = self._entries.get(name)
        if entry is None:
            raise SnowlValidationError(f"Unknown benchmark adapter '{name}'.")
        return entry.factory(**kwargs)


_DEFAULT_BENCHMARK_REGISTRY = BenchmarkRegistry()


def get_default_benchmark_registry() -> BenchmarkRegistry:
    return _DEFAULT_BENCHMARK_REGISTRY


def register_builtin_benchmarks(registry: BenchmarkRegistry | None = None) -> BenchmarkRegistry:
    registry = registry or get_default_benchmark_registry()
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
        ),
        factory=_lazy_factory("snowl.benchmarks.agent_bench_os", "AgentBenchOSBenchmarkAdapter"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.agentharm", "AgentHarmBenchmarkAdapter"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.agentharm", "AgentHarmBenchmarkAdapter", mode="benign"),
    )
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
        ),
        factory=_lazy_factory("snowl.benchmarks.bfcl", "BFCLBenchmarkAdapter"),
    )
    registry.register(
        name="coconot",
        info=BenchmarkInfo(
            name="coconot",
            description="Coconot benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="coconot",
            primary_metric="noncompliance_score",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["noncompliance", "refusal"],
        ),
        factory=_lazy_factory("snowl.benchmarks.coconot", "CoconotBenchmarkAdapter"),
    )
    registry.register(
        name="jsonl",
        info=BenchmarkInfo(
            name="jsonl",
            description="Generic JSONL benchmark adapter.",
        ),
        factory=lambda **kwargs: JsonlBenchmarkAdapter(**kwargs),
    )
    registry.register(
        name="csv",
        info=BenchmarkInfo(
            name="csv",
            description="Generic CSV benchmark adapter.",
        ),
        factory=lambda **kwargs: CsvBenchmarkAdapter(**kwargs),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.ipi_coding_agent", "IPICodingAgentBenchmarkAdapter"),
    )
    for dataset_name in ("CyberMetric-80", "CyberMetric-500", "CyberMetric-2000", "CyberMetric-10000"):
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
            ),
            factory=_lazy_factory("snowl.benchmarks.cybermetric", "CyberMetricBenchmarkAdapter", dataset_name=dataset_name),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.fortress", "FortressBenchmarkAdapter", mode="adversarial"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.fortress", "FortressBenchmarkAdapter", mode="benign"),
    )
    registry.register(
        name="strongreject",
        info=BenchmarkInfo(
            name="strongreject",
            description="StrongReject benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="strongreject",
            primary_metric="strongreject",
            higher_is_better=False,
            sample_preview_mode="dialog",
            dashboard_tags=["jailbreak", "refusal"],
            runtime_hints={
                "is_docker_like": False,
                "expected_env_type": "local",
                "scorer_hint": "benchmarks.strongreject scorer (judge-based)",
            },
        ),
        factory=_lazy_factory("snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.sec_qa", "SecQABenchmarkAdapter", variant="secqa_v1"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.sec_qa", "SecQABenchmarkAdapter", variant="secqa_v2"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.sevenllm", "SevenLLMMCQBenchmarkAdapter", language="en"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.sevenllm", "SevenLLMMCQBenchmarkAdapter", language="zh"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.wmdp", "WMDPBenchmarkAdapter"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.wmdp", "WMDPBenchmarkAdapter", variant="wmdp-chem"),
    )
    registry.register(
        name="xstest",
        info=BenchmarkInfo(
            name="xstest",
            description="XSTest benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="xstest",
            primary_metric="xstest_safety",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["refusal", "overrefusal"],
        ),
        factory=_lazy_factory("snowl.benchmarks.xstest", "XSTestBenchmarkAdapter"),
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
        ),
        factory=_lazy_factory("snowl.benchmarks.mask", "MASKBenchmarkAdapter"),
    )
    registry.register(
        name="gaia",
        info=BenchmarkInfo(
            name="gaia",
            description="GAIA general AI assistant benchmark — real-world reasoning with tool use",
            domain="agentic_capability",
            benchmark_type="capability",
            family="gaia",
            primary_metric="gaia_accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["reasoning", "tool_use", "multi_modal"],
        ),
        factory=_lazy_factory("snowl.benchmarks.gaia", "GAIABenchmarkAdapter"),
    )
    # Discover plugin benchmarks from entry_points (e.g., snowl-evals)
    _discover_plugin_benchmarks(registry)

    return registry


def _discover_plugin_benchmarks(registry: BenchmarkRegistry) -> None:
    """Discover and register benchmark adapters from snowl.benchmarks entry_points.

    Plugin benchmarks that share a name with a built-in entry are skipped
    (built-in takes precedence during the transition period).
    """
    import sys
    import importlib.metadata
    import logging

    logger = logging.getLogger(__name__)

    group = "snowl.benchmarks"
    try:
        if sys.version_info >= (3, 12):
            eps = importlib.metadata.entry_points(group=group)
        else:
            eps = importlib.metadata.entry_points().get(group, [])
    except Exception:
        return

    for ep in eps:
        if ep.name in registry._entries:
            logger.debug(
                "Plugin benchmark '%s' shadows built-in entry; keeping built-in.",
                ep.name,
            )
            continue
        try:
            register_fn = ep.load()
            if callable(register_fn):
                register_fn(registry)
                logger.info("Registered plugin benchmark '%s' from %s.", ep.name, ep.value)
        except Exception as exc:
            logger.warning("Failed to load plugin benchmark '%s': %s", ep.name, exc)


register_builtin_benchmarks()
