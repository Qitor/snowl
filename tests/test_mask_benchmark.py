"""Tests for MASK benchmark adapter."""

from snowl.benchmarks.base import validate_benchmark_adapter
from snowl.benchmarks.registry import get_default_benchmark_registry


class TestMASKAdapter:
    def test_registered(self):
        registry = get_default_benchmark_registry()
        entry = next((e for e in registry.list() if e.info.name == "mask"), None)
        assert entry is not None

    def test_metadata(self):
        registry = get_default_benchmark_registry()
        entry = next(e for e in registry.list() if e.info.name == "mask")
        assert entry.info.domain == "agentic_safety"
        assert entry.info.benchmark_type == "safety"
        assert entry.info.family == "mask"
        assert entry.info.primary_metric == "mask_score"
        assert entry.info.higher_is_better is False

    def test_adapter_info_matches_registry(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("mask")
        assert adapter.info.domain == "agentic_safety"
        assert adapter.info.benchmark_type == "safety"

    def test_validate(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("mask")
        validate_benchmark_adapter(adapter)

    def test_sample_card(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("mask")
        card = adapter.sample_card({
            "id": "m1",
            "question": "Is the sky blue?",
            "category": "factual",
            "dialog": ["Is the sky blue?"],
        })
        assert card["id"] == "m1"
        assert card["category"] == "factual"

    def test_trial_metadata(self):
        registry = get_default_benchmark_registry()
        adapter = registry.create("mask")
        meta = adapter.trial_metadata({})
        assert meta["scoring"] == "mask"
