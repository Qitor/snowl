"""Tests for SWE-Bench benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.swe_bench import SWEBenchBenchmarkAdapter
from snowl.benchmarks.swe_bench.scorer import SWEBenchPatchScorer
from snowl.core.scorer import ScoreContext


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TestSWEBenchAdapter:
    def test_default_subset(self):
        adapter = SWEBenchBenchmarkAdapter()
        assert adapter.subset == "lite"
        assert adapter.name == "swe_bench_lite"

    def test_verified_subset(self):
        adapter = SWEBenchBenchmarkAdapter(subset="verified")
        assert adapter.subset == "verified"
        assert adapter.name == "swe_bench_verified"

    def test_description_includes_subset(self):
        adapter = SWEBenchBenchmarkAdapter(subset="lite")
        assert "lite" in adapter.description.lower()

    def test_default_split(self):
        adapter = SWEBenchBenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_split(self):
        adapter = SWEBenchBenchmarkAdapter()
        assert adapter._row_split({"split": "dev"}, row_index=0) == "dev"
        assert adapter._row_split({}, row_index=0) == "test"

    def test_row_to_sample_basic(self):
        adapter = SWEBenchBenchmarkAdapter()
        row = {
            "instance_id": "django__django-12345",
            "problem_statement": "Fix the bug in Django ORM",
            "repo": "django/django",
            "base_commit": "abc123",
            "patch": "diff --git a/file.py\n@@ -1,3 +1,3 @@\n-old\n+new",
            "test_patch": "diff --git a/test.py\n@@ -1,1 +1,1 @@\n-assert False\n+assert True",
            "version": "3.2",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert "Fix the bug" in sample["input"]
        assert sample["metadata"]["instance_id"] == "django__django-12345"
        assert sample["metadata"]["repo"] == "django/django"
        assert sample["metadata"]["base_commit"] == "abc123"

    def test_row_to_sample_with_hints(self):
        adapter = SWEBenchBenchmarkAdapter()
        row = {
            "instance_id": "test-1",
            "problem_statement": "Fix the bug",
            "hints_text": "Look at the ORM layer",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert "Hints:" in sample["input"]

    def test_row_to_sample_no_problem_returns_none(self):
        adapter = SWEBenchBenchmarkAdapter()
        row = {"instance_id": "test-1"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_env_spec_has_docker(self):
        adapter = SWEBenchBenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "terminal"
        assert spec.sandbox_spec is not None
        assert spec.sandbox_spec.provider == "docker"

    def test_filter_by_repo(self):
        adapter = SWEBenchBenchmarkAdapter()
        row = {"repo": "django/django"}
        assert adapter._matches_filters(row, {"repo": "django/django"})
        assert not adapter._matches_filters(row, {"repo": "flask/flask"})


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TestSWEBenchScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = SWEBenchPatchScorer()
        assert scorer.scorer_id == "swe_bench_patch"

    def test_complete_diff(self):
        scorer = SWEBenchPatchScorer()
        output = (
            "Here's the fix:\n"
            "diff --git a/file.py b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-old line\n"
            "+new line\n"
        )
        task_result = type("R", (), {"output": output})()
        ctx = self._ctx()
        result = scorer.score(task_result, None, ctx)
        assert result["resolved"].value == 1.0
        assert result["resolved"].metadata["quality"] == "complete_diff"

    def test_partial_diff(self):
        scorer = SWEBenchPatchScorer()
        output = "diff --git a/file.py b/file.py\nsome changes but no hunk markers"
        task_result = type("R", (), {"output": output})()
        ctx = self._ctx()
        result = scorer.score(task_result, None, ctx)
        assert result["resolved"].value == 0.7
        assert result["resolved"].metadata["quality"] == "partial_diff"

    def test_code_changes(self):
        scorer = SWEBenchPatchScorer()
        output = "```diff\n-old\n+new\n```"
        task_result = type("R", (), {"output": output})()
        ctx = self._ctx()
        result = scorer.score(task_result, None, ctx)
        assert result["resolved"].value == 0.5

    def test_no_patch(self):
        scorer = SWEBenchPatchScorer()
        output = "I think the issue is in the ORM layer."
        task_result = type("R", (), {"output": output})()
        ctx = self._ctx()
        result = scorer.score(task_result, None, ctx)
        assert result["resolved"].value == 0.0
        assert result["resolved"].metadata["quality"] == "no_patch"


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

class TestSWEBenchRegistry:
    def test_lite_registered(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("swe_bench_lite")
        assert entry.name == "swe_bench_lite"

    def test_verified_registered(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("swe_bench_verified")
        assert entry.name == "swe_bench_verified"
