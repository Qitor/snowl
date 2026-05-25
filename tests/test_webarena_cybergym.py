"""Tests for WebArena and CyberGym benchmark adapters and scorers."""

import pytest

from snowl.benchmarks.webarena import WebArenaBenchmarkAdapter
from snowl.benchmarks.webarena.scorer import WebArenaScorer
from snowl.benchmarks.cybergym import CyberGymBenchmarkAdapter
from snowl.benchmarks.cybergym.scorer import CyberGymFlagScorer
from snowl.core.scorer import ScoreContext


# ---------------------------------------------------------------------------
# WebArena Adapter
# ---------------------------------------------------------------------------

class TestWebArenaAdapter:
    def test_name_and_description(self):
        adapter = WebArenaBenchmarkAdapter()
        assert adapter.name == "webarena"
        assert "web" in adapter.description.lower()

    def test_default_split(self):
        adapter = WebArenaBenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_to_sample_basic(self):
        adapter = WebArenaBenchmarkAdapter()
        row = {
            "task_id": "1",
            "intent": "Find the cheapest flight to Tokyo",
            "start_url": "https://flights.example.com",
            "site": "flights",
            "answer": "Flight AA123",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is not None
        assert "cheapest flight" in sample["input"]
        assert "flights.example.com" in sample["input"]
        assert sample["metadata"]["task_id"] == "1"
        assert sample["metadata"]["site"] == "flights"

    def test_row_to_sample_no_intent_returns_none(self):
        adapter = WebArenaBenchmarkAdapter()
        row = {"task_id": "1"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_env_spec_has_docker(self):
        adapter = WebArenaBenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "terminal"
        assert spec.sandbox_spec is not None
        assert spec.sandbox_spec.provider == "docker"

    def test_filter_by_site(self):
        adapter = WebArenaBenchmarkAdapter()
        row = {"site": "flights"}
        assert adapter._matches_filters(row, {"site": "flights"})
        assert not adapter._matches_filters(row, {"site": "shopping"})


# ---------------------------------------------------------------------------
# WebArena Scorer
# ---------------------------------------------------------------------------

class TestWebArenaScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = WebArenaScorer()
        assert scorer.scorer_id == "webarena"

    def test_exact_match(self):
        scorer = WebArenaScorer()
        task_result = type("R", (), {"output": "Flight AA123"})()
        ctx = self._ctx(sample_metadata={"answer": "Flight AA123"})
        result = scorer.score(task_result, None, ctx)
        assert result["success_rate"].value == 1.0

    def test_case_insensitive_match(self):
        scorer = WebArenaScorer()
        task_result = type("R", (), {"output": "flight aa123"})()
        ctx = self._ctx(sample_metadata={"answer": "Flight AA123"})
        result = scorer.score(task_result, None, ctx)
        assert result["success_rate"].value == 1.0

    def test_partial_match(self):
        scorer = WebArenaScorer()
        task_result = type("R", (), {"output": "The answer is Flight AA123 on Tuesday"})()
        ctx = self._ctx(sample_metadata={"answer": "flight aa123"})
        result = scorer.score(task_result, None, ctx)
        assert result["success_rate"].value == 0.5

    def test_no_match(self):
        scorer = WebArenaScorer()
        task_result = type("R", (), {"output": "Something else"})()
        ctx = self._ctx(sample_metadata={"answer": "Flight AA123"})
        result = scorer.score(task_result, None, ctx)
        assert result["success_rate"].value == 0.0


# ---------------------------------------------------------------------------
# CyberGym Adapter
# ---------------------------------------------------------------------------

class TestCyberGymAdapter:
    def test_name_and_description(self):
        adapter = CyberGymBenchmarkAdapter()
        assert adapter.name == "cybergym"
        assert "security" in adapter.description.lower() or "capability" in adapter.description.lower()

    def test_default_split(self):
        adapter = CyberGymBenchmarkAdapter()
        assert adapter.default_split == "test"

    def test_row_to_sample_basic(self):
        adapter = CyberGymBenchmarkAdapter()
        row = {
            "id": "cg-1",
            "description": "Exploit the buffer overflow vulnerability",
            "flag": "flag{overflow_123}",
            "category": "pwn",
            "difficulty": "hard",
        }
        sample = adapter._row_to_sample(row, row_index=0, row_split="pwn", selected_count=0)
        assert sample is not None
        assert "buffer overflow" in sample["input"]
        assert sample["metadata"]["challenge_id"] == "cg-1"
        assert sample["metadata"]["category"] == "pwn"
        assert sample["metadata"]["flag"] == "flag{overflow_123}"

    def test_row_to_sample_no_description_returns_none(self):
        adapter = CyberGymBenchmarkAdapter()
        row = {"id": "cg-1"}
        sample = adapter._row_to_sample(row, row_index=0, row_split="test", selected_count=0)
        assert sample is None

    def test_env_spec_has_docker(self):
        adapter = CyberGymBenchmarkAdapter()
        spec = adapter._env_spec()
        assert spec.env_type == "terminal"
        assert spec.sandbox_spec is not None
        assert spec.sandbox_spec.provider == "docker"

    def test_filter_by_category(self):
        adapter = CyberGymBenchmarkAdapter()
        row = {"category": "pwn"}
        assert adapter._matches_filters(row, {"category": "pwn"})
        assert not adapter._matches_filters(row, {"category": "web"})


# ---------------------------------------------------------------------------
# CyberGym Scorer
# ---------------------------------------------------------------------------

class TestCyberGymScorer:
    def _ctx(self, **overrides):
        defaults = dict(task_id="t1", agent_id="a1", sample_metadata={})
        defaults.update(overrides)
        return ScoreContext(**defaults)

    def test_scorer_id(self):
        scorer = CyberGymFlagScorer()
        assert scorer.scorer_id == "cybergym"

    def test_flag_match(self):
        scorer = CyberGymFlagScorer()
        task_result = type("R", (), {"output": "Captured: flag{overflow_123}"})()
        ctx = self._ctx(sample_metadata={"flag": "flag{overflow_123}"})
        result = scorer.score(task_result, None, ctx)
        assert result["flag_accuracy"].value == 1.0

    def test_flag_case_insensitive(self):
        scorer = CyberGymFlagScorer()
        task_result = type("R", (), {"output": "FLAG{OVERFLOW_123}"})()
        ctx = self._ctx(sample_metadata={"flag": "flag{overflow_123}"})
        result = scorer.score(task_result, None, ctx)
        assert result["flag_accuracy"].value == 1.0

    def test_no_flag_in_output(self):
        scorer = CyberGymFlagScorer()
        task_result = type("R", (), {"output": "I couldn't solve this challenge"})()
        ctx = self._ctx(sample_metadata={"flag": "flag{secret}"})
        result = scorer.score(task_result, None, ctx)
        assert result["flag_accuracy"].value == 0.0

    def test_ctf_pattern(self):
        scorer = CyberGymFlagScorer()
        task_result = type("R", (), {"output": "ctf{my_flag}"})()
        ctx = self._ctx(sample_metadata={"flag": "ctf{my_flag}"})
        result = scorer.score(task_result, None, ctx)
        assert result["flag_accuracy"].value == 1.0


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------

class TestRegistryLookup:
    def test_webarena_registered(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("webarena")
        assert entry.name == "webarena"

    def test_cybergym_registered(self):
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        entry = registry.create("cybergym")
        assert entry.name == "cybergym"
