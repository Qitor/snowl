"""Tests verifying that benchmark adapters return Sample instances."""

from snowl.core.sample import Sample
from snowl.benchmarks.cybench import CyBenchBenchmarkAdapter
from snowl.benchmarks.humaneval import HumanEvalBenchmarkAdapter
from snowl.benchmarks.swe_bench import SWEBenchBenchmarkAdapter
from snowl.benchmarks.math_bench import MATHBenchmarkAdapter
from snowl.benchmarks.webarena import WebArenaBenchmarkAdapter


class TestSampleReturn:
    """Verify that the 5 migrated adapters return Sample instances from _row_to_sample."""

    def _row(self, adapter, row, split="test"):
        return adapter._row_to_sample(row, row_index=0, row_split=split, selected_count=0)

    def test_cybench_returns_sample(self):
        adapter = CyBenchBenchmarkAdapter()
        row = {"id": "web-001", "description": "Find the flag", "flag": "flag{x}", "category": "web", "difficulty": "easy"}
        sample = self._row(adapter, row, split="web")
        assert isinstance(sample, Sample)
        assert sample.id == "cyber-web-001"
        assert sample["input"] == "Find the flag"

    def test_humaneval_returns_sample(self):
        adapter = HumanEvalBenchmarkAdapter()
        row = {"task_id": "HumanEval/0", "prompt": "def foo():", "test": "assert True", "entry_point": "foo", "canonical_solution": "pass"}
        sample = self._row(adapter, row)
        assert isinstance(sample, Sample)
        assert sample.id == "humaneval-0"

    def test_swe_bench_returns_sample(self):
        adapter = SWEBenchBenchmarkAdapter()
        row = {"instance_id": "swe-1", "repo": "test/repo", "base_commit": "abc", "problem_statement": "Fix bug", "patch": "--- a\n+++ b", "test_patch": "--- t\n+++ t2", "version": "3.8"}
        sample = self._row(adapter, row)
        assert isinstance(sample, Sample)
        assert sample.id == "swe-1"

    def test_math_returns_sample(self):
        adapter = MATHBenchmarkAdapter()
        row = {"problem": "What is 2+2?", "solution": "$4$", "answer": "4", "subject": "algebra", "level": 1}
        sample = self._row(adapter, row)
        assert isinstance(sample, Sample)
        assert sample.target == "4"

    def test_webarena_returns_sample(self):
        adapter = WebArenaBenchmarkAdapter()
        row = {"task_id": "1", "intent": "Find flight", "start_url": "https://example.com", "site": "flights", "answer": "AA123"}
        sample = self._row(adapter, row)
        assert isinstance(sample, Sample)
        assert sample.id == "webarena-1"

    def test_sample_dict_access_backward_compat(self):
        """Sample instances support dict-style __getitem__ for backward compatibility."""
        adapter = CyBenchBenchmarkAdapter()
        row = {"id": "x", "description": "test", "flag": "flag{x}", "category": "web", "difficulty": "easy"}
        sample = self._row(adapter, row, split="web")
        assert sample["id"] == "cyber-x"
        assert sample["input"] == "test"
        assert sample["metadata"]["category"] == "web"
