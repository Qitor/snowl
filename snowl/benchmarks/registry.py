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

from snowl.benchmarks.base import BenchmarkAdapter, BenchmarkConcurrencyProfile, BenchmarkInfo
from snowl.benchmarks.agent_bench_os import AgentBenchOSBenchmarkAdapter
from snowl.benchmarks.agentdojo import AgentDojoBenchmarkAdapter
from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.agentharm import AgentHarmBenchmarkAdapter
from snowl.benchmarks.bfcl import BFCLBenchmarkAdapter
from snowl.benchmarks.coconot import CoconotBenchmarkAdapter
from snowl.benchmarks.csv_adapter import CsvBenchmarkAdapter
from snowl.benchmarks.cybermetric import CyberMetricBenchmarkAdapter
from snowl.benchmarks.fortress import FortressBenchmarkAdapter
from snowl.benchmarks.ipi_coding_agent import IPICodingAgentBenchmarkAdapter
from snowl.benchmarks.jsonl_adapter import JsonlBenchmarkAdapter
from snowl.benchmarks.mask import MASKBenchmarkAdapter
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.benchmarks.sec_qa import SecQABenchmarkAdapter
from snowl.benchmarks.sevenllm import SevenLLMMCQBenchmarkAdapter
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.benchmarks.wmdp import WMDPBenchmarkAdapter
from snowl.benchmarks.xstest import XSTestBenchmarkAdapter
from snowl.errors import SnowlValidationError


AdapterFactory = Callable[..., BenchmarkAdapter]


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
        factory=lambda **kwargs: AgentBenchOSBenchmarkAdapter(**kwargs),
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
            concurrency_profile=BenchmarkConcurrencyProfile(
                name="agentdojo",
                api_call_amplification=5.0,
                recommended_max_running=6,
            ),
        ),
        factory=lambda **kwargs: AgentDojoBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: AgentHarmBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: AgentHarmBenchmarkAdapter(mode="benign", **kwargs),
    )
    registry.register(
        name="agentsafetybench",
        info=BenchmarkInfo(
            name="agentsafetybench",
            description="Agent-SafetyBench benchmark adapter.",
            domain="agentic_safety",
            benchmark_type="safety",
            family="agentsafetybench",
            primary_metric="safety_rate",
            higher_is_better=True,
            sample_preview_mode="dialog",
            dashboard_tags=["agent_safety"],
        ),
        factory=lambda **kwargs: AgentSafetyBenchBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: BFCLBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: CoconotBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: IPICodingAgentBenchmarkAdapter(**kwargs),
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
            factory=lambda dataset_name=dataset_name, **kwargs: CyberMetricBenchmarkAdapter(
                dataset_name=dataset_name,
                **kwargs,
            ),
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
        factory=lambda **kwargs: FortressBenchmarkAdapter(mode="adversarial", **kwargs),
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
        factory=lambda **kwargs: FortressBenchmarkAdapter(mode="benign", **kwargs),
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
        ),
        factory=lambda **kwargs: StrongRejectBenchmarkAdapter(**kwargs),
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
        ),
        factory=lambda **kwargs: TerminalBenchBenchmarkAdapter(**kwargs),
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
        ),
        factory=lambda **kwargs: OSWorldBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: SecQABenchmarkAdapter(variant="secqa_v1", **kwargs),
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
        factory=lambda **kwargs: SecQABenchmarkAdapter(variant="secqa_v2", **kwargs),
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
        factory=lambda **kwargs: SevenLLMMCQBenchmarkAdapter(language="en", **kwargs),
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
        factory=lambda **kwargs: SevenLLMMCQBenchmarkAdapter(language="zh", **kwargs),
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
            concurrency_profile=BenchmarkConcurrencyProfile(
                name="toolemu",
                api_call_amplification=30.0,
                recommended_max_running=3,
                scorer_uses_provider=True,
                scorer_provider_id="openai",
            ),
        ),
        factory=lambda **kwargs: ToolEmuBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: WMDPBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: WMDPBenchmarkAdapter(variant="wmdp-chem", **kwargs),
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
        factory=lambda **kwargs: XSTestBenchmarkAdapter(**kwargs),
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
        factory=lambda **kwargs: MASKBenchmarkAdapter(**kwargs),
    )
    return registry


register_builtin_benchmarks()
