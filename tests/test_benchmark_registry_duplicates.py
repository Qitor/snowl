"""Tests for registry duplicate handling and source precedence."""
from __future__ import annotations

import warnings

from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.registry import BenchmarkRegistry


def _info(name: str, domain: str = "test") -> BenchmarkInfo:
    return BenchmarkInfo(name=name, description=f"{name} test", domain=domain)


def test_builtin_wins_over_plugin_duplicate() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo", "builtin"), factory=lambda **kw: None, source="built-in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo", "plugin"), factory=lambda **kw: None, source="plugin")
    entry = registry._entries["foo"]
    assert entry.source == "built-in"
    assert entry.info.domain == "builtin"


def test_plugin_duplicate_is_shadowed() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo", "builtin"), factory=lambda **kw: None, source="built-in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo", "plugin"), factory=lambda **kw: None, source="plugin")
    assert "foo" in registry._shadowed
    assert len(registry._shadowed["foo"]) == 1
    assert registry._shadowed["foo"][0].source == "plugin"


def test_plugin_duplicate_emits_warning() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="built-in")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="plugin")
        assert any("shadowed" in str(x.message).lower() for x in w)


def test_list_default_excludes_shadowed() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="built-in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="plugin")
    entries = registry.list()
    assert len(entries) == 1
    assert entries[0].source == "built-in"


def test_list_include_shadowed() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="built-in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo"), factory=lambda **kw: None, source="plugin")
    entries = registry.list(include_shadowed=True)
    assert len(entries) == 2


def test_no_duplicate_no_shadow() -> None:
    registry = BenchmarkRegistry()
    registry.register("a", info=_info("a"), factory=lambda **kw: None, source="built-in")
    registry.register("b", info=_info("b"), factory=lambda **kw: None, source="plugin")
    assert len(registry._shadowed) == 0
    assert len(registry.list()) == 2


def test_plugin_overwrites_plugin() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo", "plugin1"), factory=lambda **kw: None, source="plugin")
    registry.register("foo", info=_info("foo", "plugin2"), factory=lambda **kw: None, source="plugin")
    # No built-in involved — second plugin overwrites first, no shadowing
    assert registry._entries["foo"].info.domain == "plugin2"
    assert len(registry._shadowed) == 0


def test_create_uses_canonical() -> None:
    registry = BenchmarkRegistry()
    registry.register("foo", info=_info("foo"), factory=lambda **kw: "builtin-adapter", source="built-in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        registry.register("foo", info=_info("foo"), factory=lambda **kw: "plugin-adapter", source="plugin")
    result = registry.create("foo")
    assert result == "builtin-adapter"
