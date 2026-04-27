"""Contract tests for benchmark taxonomy metadata.

Validates that all registered benchmarks have the required metadata fields
with correct enum values.
"""

from snowl.benchmarks.base import BenchmarkInfo, validate_benchmark_adapter
from snowl.benchmarks.registry import get_default_benchmark_registry


class TestBenchmarkInfoContract:
    def test_benchmark_info_extended_fields(self):
        info = BenchmarkInfo(
            name="test",
            description="Test benchmark",
            domain="cyber_offense",
            benchmark_type="capability",
            family="test",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["test"],
        )
        assert info.domain == "cyber_offense"
        assert info.benchmark_type == "capability"
        assert info.family == "test"
        assert info.primary_metric == "accuracy"
        assert info.dashboard_tags == ["test"]

    def test_benchmark_info_defaults(self):
        info = BenchmarkInfo(name="test", description="Test benchmark")
        assert info.display_name == "test"
        assert info.domain == "uncategorized"
        assert info.benchmark_type == "capability"
        assert info.family == "test"
        assert info.primary_metric == ""
        assert info.higher_is_better is True
        assert info.sample_preview_mode == "qa"
        assert info.dashboard_tags == []

    def test_display_name_defaults_to_name(self):
        info = BenchmarkInfo(name="my-bench", description="desc")
        assert info.display_name == "my-bench"

    def test_family_defaults_to_name(self):
        info = BenchmarkInfo(name="my-bench", description="desc")
        assert info.family == "my-bench"

    def test_explicit_display_name_preserved(self):
        info = BenchmarkInfo(name="my-bench", description="desc", display_name="My Benchmark")
        assert info.display_name == "My Benchmark"

    def test_explicit_family_preserved(self):
        info = BenchmarkInfo(name="my-bench", description="desc", family="my-family")
        assert info.family == "my-family"


class TestBenchmarkTypeValidation:
    def test_capability_is_valid(self):
        info = BenchmarkInfo(name="t", description="t", benchmark_type="capability")
        assert info.benchmark_type == "capability"

    def test_safety_is_valid(self):
        info = BenchmarkInfo(name="t", description="t", benchmark_type="safety")
        assert info.benchmark_type == "safety"

    def test_invalid_type_rejected_by_validate(self):
        adapter = _StubAdapter(BenchmarkInfo(name="t", description="t", benchmark_type="invalid"))
        try:
            validate_benchmark_adapter(adapter)
            assert False, "Should have raised"
        except Exception as e:
            assert "benchmark_type" in str(e)


class TestSamplePreviewModeValidation:
    def test_valid_modes(self):
        for mode in ("qa", "dialog", "tool_trace", "gui_trace", "code_trace"):
            info = BenchmarkInfo(name="t", description="t", sample_preview_mode=mode)
            assert info.sample_preview_mode == mode

    def test_invalid_mode_rejected_by_validate(self):
        adapter = _StubAdapter(BenchmarkInfo(name="t", description="t", sample_preview_mode="invalid"))
        try:
            validate_benchmark_adapter(adapter)
            assert False, "Should have raised"
        except Exception as e:
            assert "sample_preview_mode" in str(e)


class TestRegisteredBenchmarksMetadata:
    """All built-in benchmarks must have taxonomy metadata in the registry."""

    @classmethod
    def setup_class(cls):
        cls.registry = get_default_benchmark_registry()

    def test_all_benchmarks_have_domain(self):
        for entry in self.registry.list():
            assert entry.info.domain, f"{entry.info.name} missing domain"

    def test_all_benchmarks_have_valid_type(self):
        valid = {"capability", "safety"}
        for entry in self.registry.list():
            assert entry.info.benchmark_type in valid, (
                f"{entry.info.name} has invalid benchmark_type: {entry.info.benchmark_type}"
            )

    def test_all_benchmarks_have_primary_metric(self):
        # Generic adapters (jsonl, csv) may not have a primary metric
        for entry in self.registry.list():
            if entry.info.name in ("jsonl", "csv"):
                continue
            assert entry.info.primary_metric, f"{entry.info.name} missing primary_metric"

    def test_all_benchmarks_have_valid_preview_mode(self):
        valid = {"qa", "dialog", "tool_trace", "gui_trace", "code_trace"}
        for entry in self.registry.list():
            assert entry.info.sample_preview_mode in valid, (
                f"{entry.info.name} has invalid sample_preview_mode: {entry.info.sample_preview_mode}"
            )

    def test_all_benchmarks_have_family(self):
        for entry in self.registry.list():
            assert entry.info.family, f"{entry.info.name} missing family"

    def test_concrete_adapters_validate(self):
        """Adapters that can be created without required kwargs must pass validation."""
        for entry in self.registry.list():
            if entry.info.name in ("jsonl", "csv"):
                continue  # need dataset_path
            adapter = self.registry.create(entry.info.name)
            validate_benchmark_adapter(adapter)

    def test_adapter_info_matches_registry(self):
        """Adapter's info property should return the same metadata as the registry entry."""
        for entry in self.registry.list():
            if entry.info.name in ("jsonl", "csv"):
                continue
            adapter = self.registry.create(entry.info.name)
            assert adapter.info.domain == entry.info.domain, (
                f"{entry.info.name}: adapter.info.domain ({adapter.info.domain}) != registry ({entry.info.domain})"
            )
            assert adapter.info.benchmark_type == entry.info.benchmark_type

    def test_strongreject_metadata(self):
        entry = next(e for e in self.registry.list() if e.info.name == "strongreject")
        assert entry.info.domain == "agentic_safety"
        assert entry.info.benchmark_type == "safety"
        assert entry.info.family == "strongreject"
        assert entry.info.primary_metric == "strongreject"
        assert entry.info.higher_is_better is False

    def test_terminalbench_metadata(self):
        entry = next(e for e in self.registry.list() if e.info.name == "terminalbench")
        assert entry.info.domain == "cyber_offense"
        assert entry.info.benchmark_type == "capability"

    def test_osworld_metadata(self):
        entry = next(e for e in self.registry.list() if e.info.name == "osworld")
        assert entry.info.domain == "cyber_offense"
        assert entry.info.benchmark_type == "capability"
        assert "agent_capability" in entry.info.dashboard_tags

    def test_toolemu_metadata(self):
        entry = next(e for e in self.registry.list() if e.info.name == "toolemu")
        assert entry.info.domain == "agentic_safety"
        assert entry.info.benchmark_type == "safety"
        assert entry.info.higher_is_better is False

    def test_agentsafetybench_metadata(self):
        entry = next(e for e in self.registry.list() if e.info.name == "agentsafetybench")
        assert entry.info.domain == "agentic_safety"
        assert entry.info.benchmark_type == "safety"


class _StubAdapter:
    """Minimal adapter-like object for validation tests."""

    def __init__(self, info: BenchmarkInfo):
        self.info = info

    def list_splits(self) -> list[str]:
        return ["test"]

    def load_tasks(self, *, split: str, limit=None, filters=None):
        return []
