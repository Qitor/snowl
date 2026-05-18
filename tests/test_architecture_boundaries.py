"""Architecture boundary tests: core must never depend on adapter layers."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1] / "snowl" / "core"
RUNTIME_DIR = Path(__file__).resolve().parents[1] / "snowl" / "runtime"
EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"

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

# Benchmark adapter packages that runtime must NOT import directly
FORBIDDEN_RUNTIME_BENCHMARK_IMPORTS = (
    "snowl.benchmarks.osworld",
    "snowl.benchmarks.terminalbench",
    "snowl.benchmarks.agentdojo",
    "snowl.benchmarks.toolemu",
    "snowl.benchmarks.strongreject",
    "snowl.benchmarks.wmdp",
    "snowl.benchmarks.agentharm",
    "snowl.benchmarks.agentsafetybench",
    "snowl.benchmarks.bfcl",
    "snowl.benchmarks.coconot",
    "snowl.benchmarks.fortress",
    "snowl.benchmarks.ipi_coding_agent",
    "snowl.benchmarks.mask",
    "snowl.benchmarks.sec_qa",
    "snowl.benchmarks.sevenllm",
    "snowl.benchmarks.xstest",
    "snowl.benchmarks.cybermetric",
    "snowl.benchmarks.agent_bench_os",
)

# Known exceptions for runtime → benchmark imports (documented boundary violations)
# These are tracked in docs/architecture/boundary-audit.md
RUNTIME_BENCHMARK_EXCEPTIONS: dict[str, list[str]] = {
    "snowl.runtime.container_providers": ["snowl.benchmarks.osworld"],
    "snowl.runtime.policy": ["snowl.benchmarks.base", "snowl.benchmarks.registry"],
}

# Patterns that indicate real API keys in example files
_SECRET_PATTERNS = (
    "openapi-sj.sii.edu.cn",
    "openapi-qb-ai.sii.edu.cn",
    "dsv3.sii.edu.cn",
)


def _read_source(module_name: str) -> str:
    """Read the source file for a module without executing it."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return ""
    return Path(spec.origin).read_text(encoding="utf-8")


def _read_file(path: Path) -> str:
    """Read a file's text content."""
    return path.read_text(encoding="utf-8")


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


class TestRuntimeLayerBoundaries:
    """Verify that snowl.runtime does not directly import benchmark-specific adapters,
    except for known and documented exceptions."""

    def test_runtime_no_undocumented_benchmark_imports(self) -> None:
        """Runtime modules must not import benchmark-specific adapters unless documented."""
        violations: list[str] = []
        for _, module_name, _ in pkgutil.iter_modules([str(RUNTIME_DIR)]):
            full_module = f"snowl.runtime.{module_name}"
            source = _read_source(full_module)
            exceptions = RUNTIME_BENCHMARK_EXCEPTIONS.get(full_module, [])
            for prefix in FORBIDDEN_RUNTIME_BENCHMARK_IMPORTS:
                if prefix in exceptions:
                    continue
                if f"from {prefix}" in source or f"import {prefix}" in source:
                    violations.append(f"{full_module} -> {prefix}")
        if violations:
            msg = "Undocumented runtime -> benchmark imports found:\n" + "\n".join(violations)
            msg += "\n\nIf this import is necessary, add it to RUNTIME_BENCHMARK_EXCEPTIONS "
            msg += "and document it in docs/architecture/boundary-audit.md"
            assert False, msg

    def test_runtime_policy_imports_are_documented(self) -> None:
        """Verify that runtime.policy's benchmark imports match the documented exceptions."""
        source = _read_source("snowl.runtime.policy")
        for prefix in RUNTIME_BENCHMARK_EXCEPTIONS.get("snowl.runtime.policy", []):
            assert f"from {prefix}" in source or f"import {prefix}" in source, (
                f"Documented exception {prefix} not found in runtime.policy — "
                f"remove it from RUNTIME_BENCHMARK_EXCEPTIONS if it was fixed"
            )

    def test_runtime_container_providers_imports_are_documented(self) -> None:
        """Verify that container_providers' benchmark imports match documented exceptions."""
        source = _read_source("snowl.runtime.container_providers")
        for prefix in RUNTIME_BENCHMARK_EXCEPTIONS.get("snowl.runtime.container_providers", []):
            assert f"from {prefix}" in source or f"import {prefix}" in source, (
                f"Documented exception {prefix} not found in container_providers — "
                f"remove it from RUNTIME_BENCHMARK_EXCEPTIONS if it was fixed"
            )


class TestPublicAPIIntentionality:
    """Verify that public API exports from snowl.__init__ are intentional."""

    def test_snowl_init_exports_exist(self) -> None:
        """All names in snowl.__init__.__all__ must be importable."""
        import snowl

        for name in snowl.__all__:
            assert hasattr(snowl, name), f"snowl.__all__ lists '{name}' but it is not available"

    def test_core_init_exports_exist(self) -> None:
        """All names in snowl.core.__all__ must be importable."""
        import snowl.core

        for name in snowl.core.__all__:
            assert hasattr(snowl.core, name), f"snowl.core.__all__ lists '{name}' but it is not available"

    def test_snowl_init_does_not_import_benchmarks(self) -> None:
        """snowl.__init__ must not import benchmark adapters."""
        source = _read_source("snowl")
        assert "snowl.benchmarks" not in source, "snowl.__init__ imports benchmark adapters"


class TestExampleSecretHygiene:
    """Verify that example files do not contain real API keys or internal URLs."""

    def test_no_internal_proxy_urls_in_examples(self) -> None:
        """Example source files must not contain internal SII proxy URLs."""
        if not EXAMPLES_DIR.exists():
            return
        violations: list[str] = []
        for path in EXAMPLES_DIR.rglob("*.yml"):
            text = _read_file(path)
            for pattern in _SECRET_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(EXAMPLES_DIR.parent)}: {pattern}")
        for path in EXAMPLES_DIR.rglob("*.py"):
            text = _read_file(path)
            for pattern in _SECRET_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(EXAMPLES_DIR.parent)}: {pattern}")
        assert not violations, (
            "Internal proxy URLs found in examples:\n" + "\n".join(violations)
            + "\n\nReplace with environment variable placeholders."
        )

    def test_no_plaintext_api_keys_in_examples(self) -> None:
        """Example project.yml files must not contain plaintext API keys.

        Keys should use environment variable placeholders like ${OPENAI_API_KEY}.
        The pattern 'sk-...' is acceptable as a placeholder indicator.
        """
        if not EXAMPLES_DIR.exists():
            return
        violations: list[str] = []
        for path in EXAMPLES_DIR.rglob("project.yml"):
            text = _read_file(path)
            for line_no, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith("api_key:"):
                    continue
                # Extract the value part
                _, _, value = stripped.partition(":")
                value = value.strip()
                # Skip acceptable patterns
                if value.startswith("${") and value.endswith("}"):
                    continue  # env var placeholder
                if value in ("unused", "unused-env-read-by-example-code"):
                    continue  # explicitly unused
                if value == "sk-...":
                    continue  # placeholder indicator
                # Flag anything else as a potential real key
                if len(value) > 10 and not value.startswith("#"):
                    violations.append(
                        f"{path.relative_to(EXAMPLES_DIR.parent)}:{line_no}: api_key value looks like a real key"
                    )
        assert not violations, (
            "Potential real API keys found in examples:\n" + "\n".join(violations)
            + "\n\nReplace with ${SNOWL_SMOKE_API_KEY} or ${OPENAI_API_KEY} placeholders."
        )
