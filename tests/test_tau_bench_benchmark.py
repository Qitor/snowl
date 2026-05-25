"""Tests for Tau-Bench benchmark adapter and scorer."""

import pytest

from snowl.benchmarks.tau_bench import TauBenchBenchmarkAdapter
from snowl.benchmarks.tau_bench.scorer import TauBenchPolicyScorer
from snowl.core.mcp import MCPServerSpec
from snowl.core.scorer import Score, ScoreContext


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TestTauBenchAdapter:
    def test_airline_domain(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        assert adapter.domain == "airline"
        assert adapter.name == "tau_bench_airline"

    def test_retail_domain(self):
        adapter = TauBenchBenchmarkAdapter(domain="retail")
        assert adapter.domain == "retail"

    def test_env_spec_has_mcp_server(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        env_spec = adapter._env_spec()
        assert len(env_spec.mcp_servers) == 1
        assert env_spec.mcp_servers[0].name == "airline_api"
        assert env_spec.mcp_servers[0].transport == "stdio"

    def test_retail_env_spec_mcp(self):
        adapter = TauBenchBenchmarkAdapter(domain="retail")
        env_spec = adapter._env_spec()
        assert env_spec.mcp_servers[0].name == "retail_api"

    def test_row_to_sample(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        row = {
            "id": "test-001",
            "initial_prompt": "I want to change my flight",
            "expected_behavior": "Agent should verify identity before changes",
            "policy_rules": ["verify identity", "check flight status"],
            "difficulty": "easy",
        }
        sample = adapter._row_to_sample(row, row_index=1, row_split="test", selected_count=1)
        assert sample is not None
        assert sample["id"] == "tau-airline-test-001"
        assert sample["input"] == "I want to change my flight"
        assert sample["metadata"]["domain"] == "airline"
        assert sample["metadata"]["difficulty"] == "easy"

    def test_row_to_sample_with_multimodal_input(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        row = {
            "id": "test-002",
            "initial_prompt": [{"type": "text", "text": "Help me"}],
            "expected_behavior": "Agent should assist",
        }
        sample = adapter._row_to_sample(row, row_index=2, row_split="test", selected_count=1)
        assert isinstance(sample["input"], list)

    def test_list_splits(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        splits = adapter.list_splits()
        assert "test" in splits

    def test_no_samples_error_message(self):
        adapter = TauBenchBenchmarkAdapter(domain="airline")
        msg = adapter._no_samples_error("test")
        assert "airline" in msg


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TestTauBenchScorer:
    def _make_context(self, metadata=None):
        return ScoreContext(
            task_id="t1",
            agent_id="a1",
            task_metadata={"benchmark": "tau_bench"},
            sample_metadata=metadata or {},
        )

    def test_compliance_pass(self):
        scorer = TauBenchPolicyScorer()

        class FakeResult:
            answer = "I verified your identity and changed the flight as requested."

        ctx = self._make_context({
            "expected_behavior": "Agent should verify identity before changes",
        })
        scores = scorer.score(FakeResult, {}, ctx)
        assert "policy_compliance" in scores
        assert "pass_rate" in scores

    def test_no_expected_behavior(self):
        scorer = TauBenchPolicyScorer()

        class FakeResult:
            answer = "Something"

        ctx = self._make_context({})
        scores = scorer.score(FakeResult, {}, ctx)
        assert scores["policy_compliance"].value == 0.0

    def test_non_compliant_output(self):
        scorer = TauBenchPolicyScorer()

        class FakeResult:
            answer = "I changed the flight without verification."

        ctx = self._make_context({
            "expected_behavior": "Agent should verify identity before changes",
        })
        scores = scorer.score(FakeResult, {}, ctx)
        # The answer doesn't mention verifying identity
        assert scores["policy_compliance"].value == 0.0
