"""Tests for MATH benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.math_bench import MATHBenchmarkAdapter, _extract_boxed_answer
from snowl.benchmarks.math_bench.scorer import MATHAnswerScorer
from snowl.core.scorer import ScoreContext


# ---------------------------------------------------------------------------
# _extract_boxed_answer
# ---------------------------------------------------------------------------

class TestExtractBoxedAnswer:
    def test_basic(self):
        assert _extract_boxed_answer("The answer is \\boxed{42}") == "42"

    def test_fraction(self):
        assert _extract_boxed_answer("\\boxed{3/4}") == "3/4"

    def test_no_boxed(self):
        assert _extract_boxed_answer("No boxed answer here") is None

    def test_nested_braces(self):
        assert _extract_boxed_answer("\\boxed{1+2}") == "1+2"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TestMATHAdapter:
    def test_name_and_description(self):
        adapter = MATHBenchmarkAdapter()
        assert adapter.name == "math"
        assert "math" in adapter.description.lower()

    def test_default_split(self):
        adapter = MATHBenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_to_sample_basic(self):
        adapter = MATHBenchmarkAdapter()
        row = {
            "problem": "What is $2+2$?",
            "solution": "We compute $2+2=4$. The answer is \\boxed{4}",
            "answer": "4",
            "subject": "Algebra",
            "level": 1,
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert "2+2" in sample["input"]
        assert sample["metadata"]["answer"] == "4"
        assert sample["metadata"]["subject"] == "Algebra"
        assert sample["metadata"]["level"] == 1

    def test_row_to_sample_extracts_boxed_from_solution(self):
        adapter = MATHBenchmarkAdapter()
        row = {
            "problem": "Compute $3+5$.",
            "solution": "$3+5=8$ so \\boxed{8}",
            "answer": "",  # Empty — should be extracted from solution
            "subject": "Arithmetic",
            "level": 1,
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert sample["metadata"]["answer"] == "8"

    def test_row_to_sample_no_problem_returns_none(self):
        adapter = MATHBenchmarkAdapter()
        row = {"answer": "42"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_env_spec_is_local(self):
        adapter = MATHBenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "local"

    def test_filter_by_subject(self):
        adapter = MATHBenchmarkAdapter()
        row = {"subject": "Algebra"}
        assert adapter._matches_filters(row, {"subject": "Algebra"})
        assert not adapter._matches_filters(row, {"subject": "Geometry"})

    def test_filter_by_level(self):
        adapter = MATHBenchmarkAdapter()
        row = {"level": 3}
        assert adapter._matches_filters(row, {"level": 3})
        assert not adapter._matches_filters(row, {"level": 5})


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TestMATHScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = MATHAnswerScorer()
        assert scorer.scorer_id == "math_answer"

    def test_boxed_answer_correct(self):
        scorer = MATHAnswerScorer()
        task_result = type("R", (), {"output": "The answer is \\boxed{42}"})()
        ctx = self._ctx(sample_metadata={"answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_boxed_answer_wrong(self):
        scorer = MATHAnswerScorer()
        task_result = type("R", (), {"output": "The answer is \\boxed{43}"})()
        ctx = self._ctx(sample_metadata={"answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 0.0

    def test_natural_language_answer(self):
        scorer = MATHAnswerScorer()
        task_result = type("R", (), {"output": "After computing, the answer is: 42"})()
        ctx = self._ctx(sample_metadata={"answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_bare_number(self):
        scorer = MATHAnswerScorer()
        task_result = type("R", (), {"output": "Let me think...\n42"})()
        ctx = self._ctx(sample_metadata={"answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_empty_output(self):
        scorer = MATHAnswerScorer()
        task_result = type("R", (), {"output": ""})()
        ctx = self._ctx(sample_metadata={"answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 0.0

    def test_fraction_normalization(self):
        scorer = MATHAnswerScorer()
        # 3/4 should normalize to 0.75
        assert scorer._normalize_answer("3/4") == "0.75"

    def test_integer_fraction(self):
        scorer = MATHAnswerScorer()
        # 4/2 should normalize to 2
        assert scorer._normalize_answer("4/2") == "2"

    def test_negative_normalization(self):
        scorer = MATHAnswerScorer()
        assert scorer._normalize_answer("-5") == "-5"

    def test_parentheses_stripped(self):
        scorer = MATHAnswerScorer()
        assert scorer._normalize_answer("(42)") == "42"

    def test_extract_boxed_from_output(self):
        scorer = MATHAnswerScorer()
        assert scorer._extract_answer("Result: \\boxed{7}") == "7"

    def test_extract_natural_language(self):
        scorer = MATHAnswerScorer()
        assert scorer._extract_answer("The answer is: 7.") == "7"

    def test_extract_last_number(self):
        scorer = MATHAnswerScorer()
        assert scorer._extract_answer("Step 1\nStep 2\n7") == "7"

    def test_extract_empty_returns_none(self):
        scorer = MATHAnswerScorer()
        assert scorer._extract_answer("") is None


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

class TestMATHRegistry:
    def test_registered_in_benchmark_registry(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("math")
        assert entry.name == "math"
