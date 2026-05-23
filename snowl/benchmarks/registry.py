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

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkConcurrencyProfile, BenchmarkInfo, RiskDomain
from snowl.errors import SnowlValidationError

# -- Shared RiskDomain definitions ------------------------------------------------

RISK_PROMPT_INJECTION = RiskDomain(
    domain_id="prompt_injection",
    display_name="Prompt Injection",
    description="Resistance to adversarial prompt injection attacks in agentic settings.",
)
RISK_HARMFUL_TOOL_USE = RiskDomain(
    domain_id="harmful_tool_use",
    display_name="Harmful Tool Use",
    description="Propensity to use tools in ways that cause real-world harm.",
)
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
RISK_CYBER_CAPABILITY = RiskDomain(
    domain_id="cyber_capability",
    display_name="Cyber Capability",
    description="Capability to assist with offensive cybersecurity operations.",
)
RISK_CBRN_HAZARDOUS = RiskDomain(
    domain_id="cbrn_hazardous",
    display_name="CBRN Hazardous",
    description="Capability to assist with chemical, biological, radiological, or nuclear hazards.",
)
RISK_LONG_HORIZON = RiskDomain(
    domain_id="long_horizon",
    display_name="Long-Horizon Agent Risk",
    description="Risks from agents operating autonomously over extended task horizons.",
)


AdapterFactory = Callable[..., BenchmarkAdapter]


def _lazy_factory(module_path: str, class_name: str, **extra_kwargs: Any) -> AdapterFactory:
    """Create a factory that lazily imports the adapter class on first call.

    Avoids importing all benchmark adapter modules at registry initialization
    time, reducing startup cost and decoupling the registry from individual
    adapter packages.
    """
    def _factory(**kwargs: Any) -> BenchmarkAdapter:
        import importlib
        merged = {**extra_kwargs, **kwargs}
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(**merged)
    return _factory


@dataclass(frozen=True)
class RegisteredBenchmark:
    info: BenchmarkInfo
    factory: AdapterFactory
    source: str = "built-in"


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegisteredBenchmark] = {}
        self._shadowed: dict[str, list[RegisteredBenchmark]] = {}

    def register(self, name: str, info: BenchmarkInfo, factory: AdapterFactory, *, source: str = "built-in") -> None:
        key = name.strip()
        if not key:
            raise SnowlValidationError("Benchmark name must be non-empty.")
        new_entry = RegisteredBenchmark(info=info, factory=factory, source=source)
        existing = self._entries.get(key)
        if existing is not None and existing.source == "built-in" and source == "plugin":
            # Built-in wins; shadow the plugin entry
            self._shadowed.setdefault(key, []).append(new_entry)
            import warnings
            warnings.warn(
                f"Plugin benchmark '{key}' is shadowed by built-in entry. "
                f"Built-in source takes precedence during transition.",
                stacklevel=2,
            )
        else:
            self._entries[key] = new_entry

    def list(self, *, include_shadowed: bool = False) -> list[RegisteredBenchmark]:
        result = [self._entries[k] for k in sorted(self._entries.keys())]
        if include_shadowed:
            for key in sorted(self._shadowed.keys()):
                result.extend(self._shadowed[key])
        return result

    def create(self, name: str, **kwargs: Any) -> BenchmarkAdapter:
        entry = self._entries.get(name)
        if entry is None:
            raise SnowlValidationError(f"Unknown benchmark adapter '{name}'.")
        return entry.factory(**kwargs)

    def has(self, name: str) -> bool:
        return name.strip() in self._entries

    def discover_plugins(self) -> None:
        """Discover and register benchmark adapters from installed entry points.

        Looks for entry points in two groups (for backward compatibility):
        - ``snowl.benchmarks`` (preferred, matches plugin contract)
        - ``snowl.benchmark`` (legacy)

        Entry points should resolve to one of:
        - A callable that accepts this registry and registers adapters
        - A callable that returns a BenchmarkAdapter instance when called

        Adapters registered through plugins are marked with ``source="plugin"``.

        Errors during plugin loading are emitted as warnings rather than
        raising, so a broken plugin does not block the framework.
        """
        import importlib.metadata
        import warnings

        # Wrap register temporarily so plugin entries get source="plugin"
        original_register = self.register

        def _plugin_register(name, info, factory, **kwargs):
            kwargs.setdefault("source", "plugin")
            original_register(name, info, factory, **kwargs)

        self.register = _plugin_register  # type: ignore[assignment]

        seen_names: set[str] = set()
        for group in ("snowl.benchmarks", "snowl.benchmark"):
            try:
                eps = importlib.metadata.entry_points(group=group)
            except Exception:
                continue

            for ep in eps:
                if ep.name in seen_names:
                    continue
                seen_names.add(ep.name)
                try:
                    loaded = ep.load()
                    if callable(loaded):
                        # Try calling as register_fn(registry) first
                        import inspect
                        sig = inspect.signature(loaded)
                        params = list(sig.parameters)
                        if len(params) >= 1:
                            loaded(self)
                        else:
                            # No params — treat as adapter factory
                            adapter = loaded()
                            if hasattr(adapter, "info") and hasattr(adapter, "load_tasks"):
                                info = adapter.info
                                _plugin_register(ep.name, info=info, factory=lambda **kw: loaded())
                except Exception as exc:
                    warnings.warn(
                        f"Failed to load benchmark plugin '{ep.name}': {exc}",
                        stacklevel=2,
                    )

        self.register = original_register  # type: ignore[assignment]


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
            risk_domains=(),
        ),
        factory=_lazy_factory("snowl.benchmarks.agent_bench_os", "AgentBenchOSBenchmarkAdapter"),
    )
    registry.register(
        name="agentdojo",
        info=BenchmarkInfo(
            name="agentdojo",
            description="AgentDojo benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentdojo",
            primary_metric="agentdojo_score",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["prompt_injection", "tool_use", "stateful"],
            risk_domains=(RISK_PROMPT_INJECTION,),
            concurrency_profile=BenchmarkConcurrencyProfile(
                name="agentdojo",
                api_call_amplification=5.0,
                recommended_max_running=6,
            ),
        ),
        factory=_lazy_factory("snowl.benchmarks.agentdojo", "AgentDojoBenchmarkAdapter"),
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
            risk_domains=(RISK_HARMFUL_TOOL_USE,),
        ),
        factory=_lazy_factory("snowl.benchmarks.agentharm", "AgentHarmBenchmarkAdapter", mode="benign"),
    )
    registry.register(
        name="agentsafetybench",
        info=BenchmarkInfo(
            name="agentsafetybench",
            description="Agent-SafetyBench: LLM agent safety with tool-use environments.",
            display_name="Agent-SafetyBench",
            short_description="LLM agent safety benchmark with tool-use environments",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentsafetybench",
            primary_metric="agentsafetybench_safety",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["agent_safety", "tool_use", "stateful"],
            risk_domains=(RISK_HARMFUL_TOOL_USE,),
            middleware_hints={"type": "agentsafetybench", "execution_mode": "dynamic_env"},
        ),
        factory=_lazy_factory("snowl.benchmarks.agentsafetybench", "AgentSafetyBenchBenchmarkAdapter"),
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
            risk_domains=(),
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
            risk_domains=(RISK_OVER_REFUSAL,),
        ),
        factory=_lazy_factory("snowl.benchmarks.coconot", "CoconotBenchmarkAdapter"),
    )
    registry.register(
        name="jsonl",
        info=BenchmarkInfo(
            name="jsonl",
            description="Generic JSONL benchmark adapter.",
        ),
        factory=_lazy_factory("snowl.benchmarks.jsonl_adapter", "JsonlBenchmarkAdapter"),
    )
    registry.register(
        name="csv",
        info=BenchmarkInfo(
            name="csv",
            description="Generic CSV benchmark adapter.",
        ),
        factory=_lazy_factory("snowl.benchmarks.csv_adapter", "CsvBenchmarkAdapter"),
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
                risk_domains=(RISK_CYBER_CAPABILITY,),
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
            risk_domains=(RISK_OVER_REFUSAL, RISK_UNSAFE_COMPLIANCE),
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
            risk_domains=(RISK_OVER_REFUSAL,),
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
            risk_domains=(RISK_UNSAFE_COMPLIANCE,),
        ),
        factory=_lazy_factory("snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter"),
    )
    registry.register(
        name="terminalbench",
        info=BenchmarkInfo(
            name="terminalbench",
            description="Terminal-Bench benchmark adapter.",
            domain="cyber_offense",
            benchmark_type="capability",
            family="terminalbench",
            primary_metric="pass_rate",
            higher_is_better=True,
            sample_preview_mode="code_trace",
            dashboard_tags=["coding", "terminal"],
            risk_domains=(RISK_LONG_HORIZON,),
        ),
        factory=_lazy_factory("snowl.benchmarks.terminalbench", "TerminalBenchBenchmarkAdapter"),
    )
    registry.register(
        name="osworld",
        info=BenchmarkInfo(
            name="osworld",
            description="OSWorld benchmark adapter.",
            domain="cyber_offense",
            benchmark_type="capability",
            family="osworld",
            primary_metric="success_rate",
            higher_is_better=True,
            sample_preview_mode="gui_trace",
            dashboard_tags=["gui", "desktop", "agent_capability"],
            risk_domains=(RISK_LONG_HORIZON,),
        ),
        factory=_lazy_factory("snowl.benchmarks.osworld", "OSWorldBenchmarkAdapter"),
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
            risk_domains=(RISK_CYBER_CAPABILITY,),
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
            risk_domains=(RISK_CYBER_CAPABILITY,),
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
            risk_domains=(RISK_CYBER_CAPABILITY,),
        ),
        factory=_lazy_factory("snowl.benchmarks.sevenllm", "SevenLLMMCQBenchmarkAdapter", language="zh"),
    )
    registry.register(
        name="toolemu",
        info=BenchmarkInfo(
            name="toolemu",
            description="ToolEmu benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="toolemu",
            primary_metric="risk_rate",
            higher_is_better=False,
            sample_preview_mode="tool_trace",
            dashboard_tags=["tool_use", "agent_risk"],
            risk_domains=(RISK_HARMFUL_TOOL_USE, RISK_PROMPT_INJECTION),
            concurrency_profile=BenchmarkConcurrencyProfile(
                name="toolemu",
                api_call_amplification=30.0,
                recommended_max_running=3,
                scorer_uses_provider=True,
                scorer_provider_id="openai",
            ),
        ),
        factory=_lazy_factory("snowl.benchmarks.toolemu", "ToolEmuBenchmarkAdapter"),
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
            risk_domains=(RISK_CBRN_HAZARDOUS,),
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
            risk_domains=(RISK_OVER_REFUSAL,),
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
            risk_domains=(RISK_UNSAFE_COMPLIANCE,),
        ),
        factory=_lazy_factory("snowl.benchmarks.mask", "MASKBenchmarkAdapter"),
    )
    registry.register(
        name="exploitbench",
        info=BenchmarkInfo(
            name="exploitbench",
            description="ExploitBench V8 exploitation capability ladder benchmark.",
            display_name="ExploitBench",
            short_description="V8 binary exploitation capability ladder evaluation",
            domain="cyber_offense",
            benchmark_type="capability",
            family="exploitbench",
            primary_metric="exploitbench_capability_score",
            higher_is_better=True,
            sample_preview_mode="tool_trace",
            dashboard_tags=["exploitation", "v8", "binary_exploitation", "mcp"],
            risk_domains=(RISK_CYBER_CAPABILITY,),
            concurrency_profile=BenchmarkConcurrencyProfile(
                name="exploitbench",
                api_call_amplification=10.0,
                recommended_max_running=3,
            ),
        ),
        factory=_lazy_factory("snowl.benchmarks.exploitbench.adapter", "ExploitBenchBenchmarkAdapter"),
    )

    # Discover third-party plugins via entry_points
    registry.discover_plugins()
    return registry


register_builtin_benchmarks()
