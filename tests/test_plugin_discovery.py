"""Tests for plugin discovery via importlib.metadata entry_points."""

from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest

from snowl.benchmarks.registry import BenchmarkRegistry
from snowl.runtime.container_providers import ContainerProviderRegistry


def _make_entry_point(name: str, load_fn):
    """Create a mock entry point object."""
    class _MockEP:
        @property
        def name(self):
            return name

        def load(self):
            return load_fn()

    return _MockEP()


def test_benchmark_registry_discovers_plugins() -> None:
    """BenchmarkRegistry.discover_plugins loads and calls entry points."""
    registry = BenchmarkRegistry()
    called = []

    def _register_fn(reg):
        called.append(reg)

    eps = [_make_entry_point("test_plugin", lambda: _register_fn)]

    with patch("importlib.metadata.entry_points", return_value=eps):
        registry.discover_plugins()

    assert len(called) == 1
    assert called[0] is registry


def test_benchmark_registry_plugin_registers_adapter() -> None:
    """A plugin can register a benchmark adapter through discover_plugins."""
    from snowl.benchmarks.base import BenchmarkInfo

    registry = BenchmarkRegistry()

    def _register_fn(reg):
        reg.register(
            name="plugin_bench",
            info=BenchmarkInfo(name="plugin_bench", description="Plugin benchmark"),
            factory=lambda **kwargs: None,
        )

    eps = [_make_entry_point("plugin_bench", lambda: _register_fn)]

    with patch("importlib.metadata.entry_points", return_value=eps):
        registry.discover_plugins()

    # Verify the benchmark was registered (list returns entries)
    assert any(e.info.name == "plugin_bench" for e in registry.list())


def test_benchmark_registry_plugin_error_warns_not_crashes() -> None:
    """A broken plugin should emit a warning, not raise."""
    registry = BenchmarkRegistry()

    def _broken_load():
        raise ImportError("missing dependency")

    eps = [_make_entry_point("broken", _broken_load)]

    with patch("importlib.metadata.entry_points", return_value=eps):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.discover_plugins()
            assert len(w) == 1
            assert "broken" in str(w[0].message)


def test_benchmark_registry_no_plugins_no_error() -> None:
    """discover_plugins with no entry points is a no-op."""
    registry = BenchmarkRegistry()
    with patch("importlib.metadata.entry_points", return_value=[]):
        registry.discover_plugins()
    assert registry.list() == []


def test_container_provider_registry_discovers_plugins() -> None:
    """ContainerProviderRegistry.discover_plugins loads and calls entry points."""
    registry = ContainerProviderRegistry()
    called = []

    def _register_fn(reg):
        called.append(reg)

    eps = [_make_entry_point("test_provider", lambda: _register_fn)]

    with patch("importlib.metadata.entry_points", return_value=eps):
        registry.discover_plugins()

    assert len(called) == 1
    assert called[0] is registry


def test_container_provider_registry_plugin_error_warns() -> None:
    """A broken container provider plugin should emit a warning."""
    registry = ContainerProviderRegistry()

    def _broken_load():
        raise ImportError("missing dependency")

    eps = [_make_entry_point("broken", _broken_load)]

    with patch("importlib.metadata.entry_points", return_value=eps):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.discover_plugins()
            assert len(w) == 1
            assert "broken" in str(w[0].message)


def test_example_plugin_register_function() -> None:
    """Verify the example plugin's register function works when installed."""
    try:
        from snowl_bench_example import register
    except ImportError:
        pytest.skip("snowl-bench-example not installed")

    registry = BenchmarkRegistry()
    register(registry)
    assert any(e.info.name == "example" for e in registry.list())
