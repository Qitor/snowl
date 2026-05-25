"""Tests for SnowlRegistry unified facade."""

import pytest

from snowl.adapters.registry import AdapterRegistry
from snowl.benchmarks.registry import BenchmarkRegistry, get_default_benchmark_registry
from snowl.envs.provider import EnvironmentProviderRegistry
from snowl.registry import (
    DoctorResult,
    RegistryEntry,
    SnowlRegistry,
    get_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_empty_benchmark_registry() -> BenchmarkRegistry:
    return BenchmarkRegistry()


def _make_empty_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry()


def _make_empty_provider_registry() -> EnvironmentProviderRegistry:
    return EnvironmentProviderRegistry()


# ---------------------------------------------------------------------------
# RegistryEntry
# ---------------------------------------------------------------------------

class TestRegistryEntry:
    def test_construction(self):
        entry = RegistryEntry(name="test", kind="benchmark")
        assert entry.name == "test"
        assert entry.kind == "benchmark"

    def test_frozen(self):
        entry = RegistryEntry(name="test", kind="benchmark")
        with pytest.raises(AttributeError):
            entry.name = "other"


# ---------------------------------------------------------------------------
# DoctorResult
# ---------------------------------------------------------------------------

class TestDoctorResult:
    def test_ok(self):
        result = DoctorResult(ok=True)
        assert result.ok is True
        assert result.checks == []

    def test_with_checks(self):
        checks = [{"check": "test", "ok": True}]
        result = DoctorResult(ok=True, checks=checks)
        assert len(result.checks) == 1


# ---------------------------------------------------------------------------
# SnowlRegistry construction
# ---------------------------------------------------------------------------

class TestSnowlRegistryConstruction:
    def test_default_uses_global_singletons(self):
        reg = SnowlRegistry()
        # Should have benchmarks from the global registry
        benchmarks = reg.list_benchmarks()
        assert len(benchmarks) > 0

    def test_explicit_sub_registries(self):
        reg = SnowlRegistry(
            benchmarks=_make_empty_benchmark_registry(),
            adapters=_make_empty_adapter_registry(),
            env_providers=_make_empty_provider_registry(),
        )
        assert reg.list_all() == []


# ---------------------------------------------------------------------------
# list_all / list_*
# ---------------------------------------------------------------------------

class TestSnowlRegistryListing:
    def test_list_all_returns_entries_from_all_registries(self):
        reg = SnowlRegistry()
        entries = reg.list_all()
        assert len(entries) > 0
        kinds = {e.kind for e in entries}
        assert "benchmark" in kinds

    def test_list_benchmarks(self):
        reg = SnowlRegistry()
        entries = reg.list_benchmarks()
        assert all(e.kind == "benchmark" for e in entries)
        assert len(entries) > 0

    def test_list_adapters(self):
        reg = SnowlRegistry()
        entries = reg.list_adapters()
        assert all(e.kind == "adapter" for e in entries)

    def test_list_env_providers(self):
        reg = SnowlRegistry()
        entries = reg.list_env_providers()
        assert all(e.kind == "environment_provider" for e in entries)

    def test_list_all_kind_filter(self):
        reg = SnowlRegistry()
        entries = reg.list_all()
        benchmark_entries = [e for e in entries if e.kind == "benchmark"]
        assert len(benchmark_entries) == len(reg.list_benchmarks())


# ---------------------------------------------------------------------------
# info()
# ---------------------------------------------------------------------------

class TestSnowlRegistryInfo:
    def test_info_finds_benchmark(self):
        reg = SnowlRegistry()
        entry = reg.info("cybench")
        assert entry.kind == "benchmark"
        assert entry.name == "cybench"

    def test_info_finds_adapter(self):
        reg = SnowlRegistry()
        entry = reg.info("custom")
        assert entry.kind == "adapter"
        assert entry.name == "custom"

    def test_info_raises_keyerror_for_unknown(self):
        reg = SnowlRegistry()
        with pytest.raises(KeyError, match="no_such_thing"):
            reg.info("no_such_thing")


# ---------------------------------------------------------------------------
# doctor()
# ---------------------------------------------------------------------------

class TestSnowlRegistryDoctor:
    def test_doctor_with_default_registries(self):
        reg = SnowlRegistry()
        result = reg.doctor()
        assert isinstance(result, DoctorResult)
        assert result.ok is True
        assert len(result.checks) > 0

    def test_doctor_with_empty_registries(self):
        reg = SnowlRegistry(
            benchmarks=_make_empty_benchmark_registry(),
            adapters=_make_empty_adapter_registry(),
            env_providers=_make_empty_provider_registry(),
        )
        result = reg.doctor()
        assert result.ok is False
        # Should have non-empty checks for each sub-registry
        non_empty_checks = [c for c in result.checks if "non_empty" in c.get("check", "")]
        assert len(non_empty_checks) >= 3  # One for each sub-registry

    def test_doctor_checks_have_ok_field(self):
        reg = SnowlRegistry()
        result = reg.doctor()
        for check in result.checks:
            assert "ok" in check
            assert "check" in check


# ---------------------------------------------------------------------------
# get_registry singleton
# ---------------------------------------------------------------------------

class TestGetRegistry:
    def test_returns_same_instance(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_returns_snowl_registry(self):
        reg = get_registry()
        assert isinstance(reg, SnowlRegistry)
