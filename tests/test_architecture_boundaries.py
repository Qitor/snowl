"""Architecture boundary tests: core must never depend on adapter layers."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1] / "snowl" / "core"

# Packages that core must NOT import
FORBIDDEN_PREFIXES = (
    "snowl.agents",
    "snowl.benchmarks",
    "snowl.model",
    "snowl.scorer",
    "snowl.runtime",
    "snowl.tools",
    "snowl.envs",
    "snowl.cli",
    "snowl.eval",
    "snowl.ui",
    "snowl.export",
    "snowl.project_config",
    "snowl.web",
    "snowl.suite",
    "snowl.examples_lint",
)

# Third-party packages that core must NOT import
FORBIDDEN_THIRD_PARTY = (
    "httpx",
    "openai",
    "docker",
    "rich",
    "click",
    "typer",
    "jinja2",
    "yaml",
    "pydantic",
    "fastapi",
    "flask",
    "aiohttp",
    "requests",
)


def _read_source(module_name: str) -> str:
    """Read the source file for a module without executing it."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return ""
    return Path(spec.origin).read_text(encoding="utf-8")


class TestCoreLayerBoundaries:
    """Verify that snowl.core never imports from adapter or integration layers."""

    def test_core_modules_exist(self) -> None:
        """Core directory has expected modules."""
        names = {info.name for info in pkgutil.iter_modules([str(CORE_DIR)])}
        expected = {"agent", "agent_variant", "declarations", "env", "scorer", "task", "task_result", "tool"}
        assert expected <= names, f"Missing core modules: {expected - names}"

    def test_core_no_adapter_imports(self) -> None:
        """Core modules must not import from adapter/integration packages."""
        violations: list[str] = []
        for _, module_name, _ in pkgutil.iter_modules([str(CORE_DIR)]):
            source = _read_source(f"snowl.core.{module_name}")
            for prefix in FORBIDDEN_PREFIXES:
                # Check both 'from snowl.xxx import' and 'import snowl.xxx'
                if f"from {prefix}" in source or f"import {prefix}" in source:
                    violations.append(f"snowl.core.{module_name} -> {prefix}")
        assert not violations, f"Core boundary violations:\n" + "\n".join(violations)

    def test_core_no_third_party_imports(self) -> None:
        """Core modules must not import third-party packages."""
        violations: list[str] = []
        for _, module_name, _ in pkgutil.iter_modules([str(CORE_DIR)]):
            source = _read_source(f"snowl.core.{module_name}")
            for pkg in FORBIDDEN_THIRD_PARTY:
                if f"import {pkg}" in source or f"from {pkg}" in source:
                    violations.append(f"snowl.core.{module_name} -> {pkg}")
        assert not violations, f"Core third-party violations:\n" + "\n".join(violations)

    def test_core_no_circular_imports(self) -> None:
        """Core modules can all be imported successfully."""
        for _, module_name, _ in pkgutil.iter_modules([str(CORE_DIR)]):
            mod = importlib.import_module(f"snowl.core.{module_name}")
            assert mod is not None

    def test_core_init_exports_only_core(self) -> None:
        """snowl.core.__init__ must not re-export from non-core packages."""
        source = _read_source("snowl.core")
        for prefix in FORBIDDEN_PREFIXES:
            assert f"from {prefix}" not in source, f"core __init__ imports {prefix}"
