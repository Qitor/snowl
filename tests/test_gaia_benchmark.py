"""Tests for GAIA benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.gaia import GAIABenchmarkAdapter
from snowl.benchmarks.gaia.scorer import GAIAScorer
from snowl.core.sample import Sample
from snowl.core.scorer import Score, ScoreContext


# ---------------------------------------------------------------------------
# GAIA Adapter
# ---------------------------------------------------------------------------

class TestGAIAAdapter:
    def test_name_and_description(self):
        adapter = GAIABenchmarkAdapter()
        assert adapter.name == "gaia"
        assert "assistant" in adapter.description.lower() or "reasoning" in adapter.description.lower()

    def test_default_split(self):
        adapter = GAIABenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_to_sample_basic(self):
        adapter = GAIABenchmarkAdapter()
        row = {
            "task_id": "gaia-1",
            "question": "What is the population of Tokyo?",
            "level": 1,
            "final_answer": "13,960,000",
            "file_name": "",
            "file_path": "",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="L1", selected_count=0)
        assert sample is not None
        assert isinstance(sample, Sample)
        assert "population" in sample.input
        assert sample.metadata["level"] == "L1"
        assert sample.target == "13,960,000"

    def test_row_to_sample_with_file(self):
        adapter = GAIABenchmarkAdapter()
        row = {
            "task_id": "gaia-2",
            "question": "Analyze the attached spreadsheet",
            "level": 2,
            "final_answer": "42",
            "file_name": "data.xlsx",
            "file_path": "/tmp/data.xlsx",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="L2", selected_count=0)
        assert sample is not None
        assert "data.xlsx" in sample.input

    def test_row_to_sample_no_question_returns_none(self):
        adapter = GAIABenchmarkAdapter()
        row = {"task_id": "gaia-3"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_row_split_by_level(self):
        adapter = GAIABenchmarkAdapter()
        assert adapter._row_split({"level": 1}, row_index=0) == "L1"
        assert adapter._row_split({"level": 2}, row_index=0) == "L2"
        assert adapter._row_split({"level": 3}, row_index=0) == "L3"

    def test_filter_by_level(self):
        adapter = GAIABenchmarkAdapter()
        row = {"level": 1}
        assert adapter._matches_filters(row, {"level": "L1"})
        assert not adapter._matches_filters(row, {"level": "L2"})

    def test_env_spec_has_terminal(self):
        adapter = GAIABenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "terminal"


# ---------------------------------------------------------------------------
# GAIA Scorer
# ---------------------------------------------------------------------------

class TestGAIAScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = GAIAScorer()
        assert scorer.scorer_id == "gaia"

    def test_exact_match(self):
        scorer = GAIAScorer()
        task_result = type("R", (), {"output": "13,960,000"})()
        ctx = self._ctx(sample_metadata={"final_answer": "13,960,000"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_case_insensitive_match(self):
        scorer = GAIAScorer()
        task_result = type("R", (), {"output": "Tokyo"})()
        ctx = self._ctx(sample_metadata={"final_answer": "tokyo"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_partial_match(self):
        scorer = GAIAScorer()
        task_result = type("R", (), {"output": "The answer is 42 people"})()
        ctx = self._ctx(sample_metadata={"final_answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 0.5

    def test_no_match(self):
        scorer = GAIAScorer()
        task_result = type("R", (), {"output": "Something completely different"})()
        ctx = self._ctx(sample_metadata={"final_answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 0.0

    def test_answer_extraction_the_answer_is(self):
        scorer = GAIAScorer()
        task_result = type("R", (), {"output": "Based on analysis, the answer is 42."})()
        ctx = self._ctx(sample_metadata={"final_answer": "42"})
        result = scorer.score(task_result, None, ctx)
        assert result["accuracy"].value == 1.0

    def test_normalization_percent(self):
        scorer = GAIAScorer()
        assert scorer._normalize("50 percent") == "50%"
        assert scorer._normalize("50%") == "50%"

    def test_normalization_whitespace(self):
        scorer = GAIAScorer()
        assert scorer._normalize("  42  ") == "42"


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

class TestGAIARegistry:
    def test_gaia_registered(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("gaia")
        assert entry.name == "gaia"
