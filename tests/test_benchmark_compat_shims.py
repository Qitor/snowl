"""Tests for deprecation shims in phase_2_simple benchmark __init__.py files."""
from __future__ import annotations

import importlib
import sys
import warnings

import pytest

# Modules that should emit DeprecationWarning when imported
_DEPRECATED_MODULES = [
    "snowl.benchmarks.strongreject",
    "snowl.benchmarks.xstest",
    "snowl.benchmarks.wmdp",
    "snowl.benchmarks.sec_qa",
    "snowl.benchmarks.cybermetric",
    "snowl.benchmarks.coconot",
    "snowl.benchmarks.mask",
    "snowl.benchmarks.sevenllm",
    "snowl.benchmarks.fortress",
    "snowl.benchmarks.agentharm",
    "snowl.benchmarks.agent_bench_os",
    "snowl.benchmarks.bfcl",
    "snowl.benchmarks.ipi_coding_agent",
]

# Modules that should NOT emit DeprecationWarning (phase_3_heavy / keep_in_core)
_NON_DEPRECATED_MODULES = [
    "snowl.benchmarks.agentdojo",
    "snowl.benchmarks.toolemu",
    "snowl.benchmarks.agentsafetybench",
    "snowl.benchmarks.osworld",
    "snowl.benchmarks.terminalbench",
]


@pytest.mark.parametrize("module_name", _DEPRECATED_MODULES)
def test_deprecated_module_emits_warning(module_name: str) -> None:
    # Remove from sys.modules so re-import triggers the warning
    sys.modules.pop(module_name, None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module(module_name)
        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, (
            f"Expected DeprecationWarning when importing {module_name}, got {[str(x.message) for x in w]}"
        )


@pytest.mark.parametrize("module_name", _DEPRECATED_MODULES)
def test_deprecated_warning_mentions_snowl_evals(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module(module_name)
        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        msg = str(deprecation_warnings[0].message).lower()
        assert "snowl-evals" in msg or "snowl_evals" in msg, (
            f"Deprecation warning for {module_name} should mention snowl-evals: {deprecation_warnings[0].message}"
        )


@pytest.mark.parametrize("module_name", _NON_DEPRECATED_MODULES)
def test_non_deprecated_module_no_warning(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        importlib.import_module(module_name)
        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        # Filter out warnings from transitive imports of deprecated sub-modules
        direct = [x for x in deprecation_warnings if module_name in str(x.message)]
        assert len(direct) == 0, (
            f"{module_name} should not emit DeprecationWarning about itself, got: {[str(x.message) for x in direct]}"
        )


def test_deprecated_modules_still_export_symbols() -> None:
    """Deprecated shims must still re-export the adapter/scorer symbols for backwards compat."""
    expected_exports: dict[str, list[str]] = {
        "snowl.benchmarks.strongreject": ["StrongRejectBenchmarkAdapter"],
        "snowl.benchmarks.xstest": ["XSTestBenchmarkAdapter"],
        "snowl.benchmarks.wmdp": ["WMDPBenchmarkAdapter"],
        "snowl.benchmarks.sec_qa": ["SecQABenchmarkAdapter"],
        "snowl.benchmarks.cybermetric": ["CyberMetricBenchmarkAdapter"],
        "snowl.benchmarks.coconot": ["CoconotBenchmarkAdapter"],
        "snowl.benchmarks.mask": ["MASKBenchmarkAdapter"],
        "snowl.benchmarks.sevenllm": ["SevenLLMMCQBenchmarkAdapter"],
        "snowl.benchmarks.fortress": ["FortressBenchmarkAdapter"],
        "snowl.benchmarks.agentharm": ["AgentHarmBenchmarkAdapter"],
        "snowl.benchmarks.agent_bench_os": ["AgentBenchOSBenchmarkAdapter"],
        "snowl.benchmarks.bfcl": ["BFCLBenchmarkAdapter"],
        "snowl.benchmarks.ipi_coding_agent": ["IPICodingAgentBenchmarkAdapter"],
    }
    for module_name, symbols in expected_exports.items():
        mod = importlib.import_module(module_name)
        for sym in symbols:
            assert hasattr(mod, sym), f"{module_name} should export {sym}"
