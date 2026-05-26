"""Snowl post-install health check command."""

from __future__ import annotations


def _cmd_check() -> int:
    """Run quick health diagnostics for the snowl installation."""
    import sys

    checks_passed = 0
    checks_failed = 0

    # 1. Core import
    try:
        import snowl
        version = snowl.__version__
        print(f"  [OK] snowl import: v{version}")
        checks_passed += 1
    except Exception as exc:
        print(f"  [FAIL] snowl import: {exc}")
        checks_failed += 1

    # 2. Benchmark registry
    try:
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entries = registry.list()
        print(f"  [OK] Benchmark registry: {len(entries)} benchmarks available")
        checks_passed += 1
    except Exception as exc:
        print(f"  [FAIL] Benchmark registry: {exc}")
        checks_failed += 1

    # 3. snowl-evals plugin
    try:
        from importlib.metadata import entry_points
        plugin_eps = entry_points(group="snowl.benchmarks")
        if plugin_eps:
            print(f"  [OK] snowl-evals plugins: {len(plugin_eps)} benchmark entries discovered")
        else:
            print("  [OK] snowl-evals plugins: none (install snowl-evals for more benchmarks)")
        checks_passed += 1
    except Exception as exc:
        print(f"  [FAIL] Plugin discovery: {exc}")
        checks_failed += 1

    # 4. Adapter registry
    try:
        from snowl.adapters.registry import get_default_adapter_registry
        adapter_reg = get_default_adapter_registry()
        frameworks = adapter_reg.list_frameworks()
        print(f"  [OK] Adapter registry: {len(frameworks)} frameworks ({', '.join(frameworks)})")
        checks_passed += 1
    except Exception as exc:
        print(f"  [FAIL] Adapter registry: {exc}")
        checks_failed += 1

    # 5. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f"  [OK] Python version: {py_ver}")
        checks_passed += 1
    else:
        print(f"  [FAIL] Python version: {py_ver} (requires >=3.10)")
        checks_failed += 1

    # Summary
    print()
    if checks_failed == 0:
        print(f"All {checks_passed} checks passed.")
        return 0
    else:
        print(f"{checks_passed} passed, {checks_failed} failed.")
        return 1
