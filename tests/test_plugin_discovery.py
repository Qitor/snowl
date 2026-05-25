"""Tests for snowl.benchmarks plugin discovery via importlib.metadata entry_points."""

import importlib.metadata
from unittest.mock import patch, MagicMock

from snowl.benchmarks.registry import (
    BenchmarkRegistry,
    BenchmarkInfo,
    register_builtin_benchmarks,
    _discover_plugin_benchmarks,
)


class TestPluginDiscovery:
    def test_discover_plugin_benchmarks_registers_new_entry(self):
        registry = BenchmarkRegistry()
        mock_ep = MagicMock()
        mock_ep.name = "test_plugin_bench"
        mock_fn = MagicMock()
        mock_ep.load.return_value = mock_fn

        with patch.object(importlib.metadata, "entry_points", return_value=[mock_ep]):
            _discover_plugin_benchmarks(registry)

        mock_fn.assert_called_once_with(registry)

    def test_plugin_does_not_shadow_builtin(self):
        """If a plugin has the same name as a built-in, the built-in wins."""
        registry = BenchmarkRegistry()
        registry.register(
            name="strongreject",
            info=BenchmarkInfo(name="strongreject", description="built-in"),
            factory=lambda **kw: None,
        )

        mock_ep = MagicMock()
        mock_ep.name = "strongreject"
        mock_fn = MagicMock()
        mock_ep.load.return_value = mock_fn

        with patch.object(importlib.metadata, "entry_points", return_value=[mock_ep]):
            _discover_plugin_benchmarks(registry)

        mock_fn.assert_not_called()

    def test_broken_plugin_entry_point_is_skipped(self):
        """A plugin that fails to load should not break discovery."""
        registry = BenchmarkRegistry()

        mock_ep = MagicMock()
        mock_ep.name = "broken_bench"
        mock_ep.load.side_effect = ImportError("missing dep")

        with patch.object(importlib.metadata, "entry_points", return_value=[mock_ep]):
            _discover_plugin_benchmarks(registry)

        assert len(registry.list()) == 0

    def test_register_builtin_discovers_plugins(self):
        """Full register_builtin_benchmarks should include plugin discovery."""
        mock_ep = MagicMock()
        mock_ep.name = "plugin_test_bench_r3"
        mock_register = MagicMock()
        mock_ep.load.return_value = mock_register

        with patch.object(importlib.metadata, "entry_points", return_value=[mock_ep]):
            registry = register_builtin_benchmarks()

        names = {rb.info.name for rb in registry.list()}
        assert "strongreject" in names
        mock_register.assert_called_once()

    def test_non_callable_entry_point_is_skipped(self):
        """A plugin entry point that loads to a non-callable should be skipped."""
        registry = BenchmarkRegistry()

        mock_ep = MagicMock()
        mock_ep.name = "not_callable_bench"
        mock_ep.load.return_value = "not a function"

        with patch.object(importlib.metadata, "entry_points", return_value=[mock_ep]):
            _discover_plugin_benchmarks(registry)

        assert len(registry.list()) == 0
