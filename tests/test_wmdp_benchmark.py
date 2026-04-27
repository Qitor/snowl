"""Tests for WMDP benchmark adapters."""

from snowl.benchmarks.base import validate_benchmark_adapter
from snowl.benchmarks.registry import get_default_benchmark_registry


class TestWMDPCyberAdapter:
    def test_registered(self):
        registry = get_default_benchmark_registry()
        entry = next((e for e in registry.list() if e.info.name == "wmdp-cyber"), None)
        assert entry is not None

    def test_metadata(self):
        registry = get_default_benchmark_registry()
        entry = next(e for e in registry.list() if e.info.name == "wmdp-cyber")
        assert entry.info.domain == "cyber_offense"
        assert entry.info.benchmark_type == "capability"
        assert entry.info.family == "wmdp"
        assert entry.info.primary_metric == "accuracy"

    def test_adapter_info_matches_registry(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-cyber")
        assert adapter.info.domain == "cyber_offense"
        assert adapter.info.benchmark_type == "capability"

    def test_validate(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-cyber")
        validate_benchmark_adapter(adapter)

    def test_sample_card(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-cyber")
        card = adapter.sample_card({"id": "q1", "question": "What is 2+2?", "choices": ["3", "4", "5"]})
        assert card["id"] == "q1"
        assert card["choices_count"] == 3

    def test_trial_metadata(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-cyber")
        meta = adapter.trial_metadata({})
        assert meta["scoring"] == "accuracy"


class TestWMDPChemAdapter:
    def test_registered(self):
        registry = get_default_benchmark_registry()
        entry = next((e for e in registry.list() if e.info.name == "wmdp-chem"), None)
        assert entry is not None

    def test_metadata(self):
        registry = get_default_benchmark_registry()
        entry = next(e for e in registry.list() if e.info.name == "wmdp-chem")
        assert entry.info.domain == "chemical_risks"
        assert entry.info.benchmark_type == "capability"
        assert entry.info.family == "wmdp"

    def test_adapter_info_matches_registry(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-chem")
        assert adapter.info.domain == "chemical_risks"
        assert adapter.info.benchmark_type == "capability"

    def test_validate(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("wmdp-chem")
        validate_benchmark_adapter(adapter)
