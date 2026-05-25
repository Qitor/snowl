"""Tests for CyBench benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.cybench import CyBenchBenchmarkAdapter
from snowl.benchmarks.cybench.scorer import CyBenchFlagScorer
from snowl.core.scorer import ScoreContext


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TestCyBenchAdapter:
    def test_basic_creation(self):
        adapter = CyBenchBenchmarkAdapter()
        assert adapter.name == "cybench"

    def test_env_spec_terminal_with_sandbox(self):
        adapter = CyBenchBenchmarkAdapter()
        env_spec = adapter._env_spec()
        assert env_spec.env_type == "terminal"
        assert env_spec.sandbox_spec is not None
        assert env_spec.sandbox_spec.provider == "docker"

    def test_row_to_sample(self):
        adapter = CyBenchBenchmarkAdapter()
        row = {
            "id": "web-001",
            "description": "Find the flag in the web application",
            "flag": "flag{sql_injection}",
            "category": "web",
            "difficulty": "easy",
            "hints": ["Look at the login form"],
        }
        sample = adapter._row_to_sample(row, row_index=1, row_split="web", selected_count=1)
        assert sample is not None
        assert sample["id"] == "cyber-web-001"
        assert sample["input"] == "Find the flag in the web application"
        assert sample["target"] == "flag{sql_injection}"
        assert sample["metadata"]["category"] == "web"
        assert sample["metadata"]["flag"] == "flag{sql_injection}"

    def test_row_split_by_category(self):
        adapter = CyBenchBenchmarkAdapter()
        row = {"category": "crypto"}
        assert adapter._row_split(row) == "crypto"

    def test_matches_category_filter(self):
        adapter = CyBenchBenchmarkAdapter()
        row = {"category": "web", "difficulty": "easy"}
        assert adapter._matches_filters(row, {"category": "web"})
        assert not adapter._matches_filters(row, {"category": "crypto"})

    def test_matches_difficulty_filter(self):
        adapter = CyBenchBenchmarkAdapter()
        row = {"category": "web", "difficulty": "easy"}
        assert adapter._matches_filters(row, {"difficulty": "easy"})
        assert not adapter._matches_filters(row, {"difficulty": "hard"})

    def test_no_samples_error_message(self):
        adapter = CyBenchBenchmarkAdapter()
        msg = adapter._no_samples_error("web")
        assert "CyBench" in msg


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TestCyBenchScorer:
    def _make_context(self, metadata=None):
        return ScoreContext(
            task_id="t1",
            agent_id="a1",
            task_metadata={"benchmark": "cybench"},
            sample_metadata=metadata or {},
        )

    def test_flag_matched(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = "The flag is flag{sql_injection}"

        ctx = self._make_context({"flag": "flag{sql_injection}"})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["flag_accuracy"].value == 1.0

    def test_flag_not_found(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = "I couldn't find the flag"

        ctx = self._make_context({"flag": "flag{sql_injection}"})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["flag_accuracy"].value == 0.0

    def test_flag_case_insensitive(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = "FLAG{SQL_INJECTION}"

        ctx = self._make_context({"flag": "flag{sql_injection}"})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["flag_accuracy"].value == 1.0

    def test_no_expected_flag(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = "something"

        ctx = self._make_context({})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["flag_accuracy"].value == 0.0

    def test_flag_in_trace_messages(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = ""

        trace = {"messages": [{"content": "I found: flag{xss_attack}"}]}
        ctx = self._make_context({"flag": "flag{xss_attack}"})
        scores = scorer.score(FakeResult, trace, ctx)
        assert scores["flag_accuracy"].value == 1.0

    def test_ctf_format_flag(self):
        scorer = CyBenchFlagScorer()

        class FakeResult:
            answer = "CTF{buffer_overflow}"

        ctx = self._make_context({"flag": "CTF{buffer_overflow}"})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["flag_accuracy"].value == 1.0
