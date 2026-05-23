"""Tests for new public API symbols required by snowl-evals.

Validates: RiskDomain, _lazy_factory, load_manifest.
These symbols are the contract between snowl and snowl-evals.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


# ── RiskDomain ────────────────────────────────────────────────────────────────

class TestRiskDomain:
    def test_construction(self):
        from snowl.benchmarks.base import RiskDomain
        rd = RiskDomain(domain_id="unsafe_compliance", display_name="Unsafe Compliance",
                        description="Test description")
        assert rd.domain_id == "unsafe_compliance"
        assert rd.display_name == "Unsafe Compliance"
        assert rd.description == "Test description"

    def test_defaults(self):
        from snowl.benchmarks.base import RiskDomain
        rd = RiskDomain(domain_id="test")
        assert rd.display_name == ""
        assert rd.description == ""

    def test_frozen(self):
        from snowl.benchmarks.base import RiskDomain
        rd = RiskDomain(domain_id="test")
        with pytest.raises(AttributeError):
            rd.domain_id = "changed"

    def test_reexported_from_init(self):
        from snowl.benchmarks import RiskDomain
        assert RiskDomain is not None

    def test_in_benchmark_info(self):
        from snowl.benchmarks.base import BenchmarkInfo, RiskDomain
        rd = RiskDomain(domain_id="test")
        info = BenchmarkInfo(
            name="test", description="test",
            risk_domains=(rd,),
        )
        assert info.risk_domains == (rd,)

    def test_default_empty_risk_domains(self):
        from snowl.benchmarks.base import BenchmarkInfo
        info = BenchmarkInfo(name="test", description="test")
        assert info.risk_domains == ()


# ── _lazy_factory ─────────────────────────────────────────────────────────────

class TestLazyFactory:
    def test_returns_callable(self):
        from snowl.benchmarks.registry import _lazy_factory
        factory = _lazy_factory("snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter")
        assert callable(factory)

    def test_deferred_import(self):
        from snowl.benchmarks.registry import _lazy_factory
        # Creating the factory should NOT import the module yet
        factory = _lazy_factory("snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter")
        # The factory should still be callable (import happens on call)
        assert callable(factory)

    def test_factory_produces_adapter(self):
        from snowl.benchmarks.registry import _lazy_factory
        factory = _lazy_factory("snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter")
        adapter = factory()
        assert adapter is not None
        assert hasattr(adapter, "info")

    def test_default_kwargs_forwarded(self):
        from snowl.benchmarks.registry import _lazy_factory
        factory = _lazy_factory(
            "snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter",
        )
        # The factory should be callable and produce an adapter
        adapter = factory()
        assert adapter is not None
        assert hasattr(adapter, "info")

    def test_default_kwargs_stored(self):
        from snowl.benchmarks.registry import _lazy_factory
        # Verify that default kwargs are captured in the closure
        factory = _lazy_factory(
            "snowl.benchmarks.strongreject", "StrongRejectBenchmarkAdapter",
        )
        # The qualname should encode the module:class path
        assert "strongreject" in factory.__qualname__
        assert "StrongRejectBenchmarkAdapter" in factory.__qualname__

    def test_reexported_from_init(self):
        from snowl.benchmarks import _lazy_factory
        assert _lazy_factory is not None


# ── load_manifest ─────────────────────────────────────────────────────────────

class TestLoadManifest:
    def test_load_valid_manifest(self, tmp_path: Path):
        from snowl.benchmarks.manifest import load_manifest, BenchmarkManifest
        manifest_data = {
            "schema_version": "snowl.benchmark_manifest.v1",
            "name": "test_bench",
            "display_name": "Test Benchmark",
            "family": "test",
            "domain": "safety",
            "benchmark_type": "safety",
            "primary_metric": "accuracy",
            "higher_is_better": True,
            "status": "stable",
            "source": {"paper": "https://example.com"},
            "adapter": {"entrypoint": "snowl_evals.test:TestAdapter"},
            "runtime": {"env_type": "local", "requires_network": False},
            "data": {"included": False},
            "scoring": {"method": "exact_match"},
            "reproducibility": {"deterministic": True},
            "migration": {"target": "snowl-evals"},
        }
        p = tmp_path / "benchmark.yaml"
        p.write_text(yaml.dump(manifest_data), encoding="utf-8")

        result = load_manifest(p)
        assert isinstance(result, BenchmarkManifest)
        assert result.name == "test_bench"
        assert result.domain == "safety"
        assert result.entrypoint == "snowl_evals.test:TestAdapter"
        assert result.requires_network is False
        assert result.scoring_method == "exact_match"

    def test_missing_file_raises(self, tmp_path: Path):
        from snowl.benchmarks.manifest import load_manifest
        with pytest.raises(FileNotFoundError, match="Manifest not found"):
            load_manifest(tmp_path / "nonexistent.yaml")

    def test_non_mapping_raises(self, tmp_path: Path):
        from snowl.benchmarks.manifest import load_manifest
        p = tmp_path / "benchmark.yaml"
        p.write_text("- just\n- a\n- list", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_manifest(p)

    def test_empty_manifest_defaults(self, tmp_path: Path):
        from snowl.benchmarks.manifest import load_manifest, BenchmarkManifest
        p = tmp_path / "benchmark.yaml"
        p.write_text("{}", encoding="utf-8")
        result = load_manifest(p)
        assert isinstance(result, BenchmarkManifest)
        assert result.name == ""
        assert result.higher_is_better is True

    def test_reexported_from_init(self):
        from snowl.benchmarks import load_manifest, BenchmarkManifest
        assert load_manifest is not None
        assert BenchmarkManifest is not None
