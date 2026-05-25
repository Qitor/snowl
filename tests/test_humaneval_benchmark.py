"""Tests for HumanEval benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.humaneval import HumanEvalBenchmarkAdapter
from snowl.benchmarks.humaneval.scorer import HumanEvalExecutionScorer
from snowl.core.scorer import ScoreContext


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TestHumanEvalAdapter:
    def test_name_and_description(self):
        adapter = HumanEvalBenchmarkAdapter()
        assert adapter.name == "humaneval"
        assert "code generation" in adapter.description.lower()

    def test_default_split(self):
        adapter = HumanEvalBenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_split_always_test(self):
        adapter = HumanEvalBenchmarkAdapter()
        assert adapter._row_split({"task_id": "HumanEval/0"}, row_index=0) == "test"

    def test_row_to_sample_basic(self):
        adapter = HumanEvalBenchmarkAdapter()
        row = {
            "task_id": "HumanEval/0",
            "prompt": "def has_close_elements(numbers: List[float], threshold: float) -> bool:\n",
            "test": "assert has_close_elements([1.0, 2.0, 3.0], 0.5) == False",
            "entry_point": "has_close_elements",
            "canonical_solution": "    for i in range(len(numbers)):\n        for j in range(i+1, len(numbers)):\n            if abs(numbers[i] - numbers[j]) < threshold:\n                return True\n    return False\n",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert "has_close_elements" in sample["input"]
        assert sample["metadata"]["entry_point"] == "has_close_elements"
        assert sample["metadata"]["task_id"] == "HumanEval/0"
        assert sample["metadata"]["test"] == row["test"]

    def test_row_to_sample_no_prompt_returns_none(self):
        adapter = HumanEvalBenchmarkAdapter()
        row = {"task_id": "HumanEval/0"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_env_spec_is_local(self):
        adapter = HumanEvalBenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "local"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TestHumanEvalScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = HumanEvalExecutionScorer()
        assert scorer.scorer_id == "humaneval_execution"

    def test_correct_function_definition(self):
        scorer = HumanEvalExecutionScorer()
        task_result = type("R", (), {"output": "def has_close_elements(numbers, threshold):\n    return True"})()
        ctx = self._ctx(sample_metadata={"entry_point": "has_close_elements", "test": "assert ..."})
        result = scorer.score(task_result, None, ctx)
        assert result["pass_at_1"].value == 1.0

    def test_wrong_function_definition(self):
        scorer = HumanEvalExecutionScorer()
        task_result = type("R", (), {"output": "def wrong_function():\n    pass"})()
        ctx = self._ctx(sample_metadata={"entry_point": "has_close_elements", "test": "assert ..."})
        result = scorer.score(task_result, None, ctx)
        assert result["pass_at_1"].value == 0.0

    def test_code_with_return(self):
        scorer = HumanEvalExecutionScorer()
        task_result = type("R", (), {"output": "Here's the solution:\nreturn True\n"})()
        ctx = self._ctx(sample_metadata={"entry_point": "has_close_elements", "test": "assert ..."})
        result = scorer.score(task_result, None, ctx)
        # Has "return" and length > 20 → partial credit
        assert result["pass_at_1"].value == 0.5

    def test_empty_output(self):
        scorer = HumanEvalExecutionScorer()
        task_result = type("R", (), {"output": ""})()
        ctx = self._ctx(sample_metadata={"entry_point": "has_close_elements", "test": "assert ..."})
        result = scorer.score(task_result, None, ctx)
        assert result["pass_at_1"].value == 0.0

    def test_dict_task_result(self):
        scorer = HumanEvalExecutionScorer()
        task_result = {"output": "def has_close_elements(n, t):\n    return True"}
        ctx = self._ctx(sample_metadata={"entry_point": "has_close_elements", "test": "assert ..."})
        result = scorer.score(task_result, None, ctx)
        assert result["pass_at_1"].value == 1.0


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

class TestHumanEvalRegistry:
    def test_registered_in_benchmark_registry(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("humaneval")
        assert entry.name == "humaneval"
