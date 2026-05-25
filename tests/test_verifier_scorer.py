"""Tests for VerifierScorer: reward parsing, SEPARATE mode delegation."""

import pytest

from snowl.core.scorer import Score, ScoreContext
from snowl.scorer.verifier import VerifierScorer, _parse_reward


def _ctx(**overrides):
    defaults = dict(task_id="t1", agent_id="a1")
    defaults.update(overrides)
    return ScoreContext(**defaults)


# ---------------------------------------------------------------------------
# _parse_reward
# ---------------------------------------------------------------------------

class TestParseReward:
    def test_single_float(self):
        val, meta = _parse_reward("0.75", "/logs/verifier/reward.txt")
        assert val == 0.75
        assert "reward_text" in meta

    def test_reward_json_single(self):
        content = '{"reward": 0.9}'
        val, meta = _parse_reward(content, "/logs/verifier/reward.json")
        assert val == 0.9
        assert "reward_json" in meta

    def test_reward_json_dimensions(self):
        content = '{"dimensions": {"correctness": 1.0, "style": 0.5}}'
        val, meta = _parse_reward(content, "/logs/verifier/reward.json")
        assert val == 0.75  # average of 1.0 and 0.5
        assert "reward_dimensions" in meta

    def test_empty_content(self):
        val, meta = _parse_reward("", "/logs/verifier/reward.txt")
        assert val == 0.0
        assert meta.get("reward_empty") is True

    def test_multiline_last_float(self):
        val, meta = _parse_reward("some output\n0.6\n", "/logs/verifier/reward.txt")
        assert val == 0.6

    def test_invalid_content(self):
        val, meta = _parse_reward("not a number", "/logs/verifier/reward.txt")
        assert val == 0.0
        assert meta.get("reward_parse_failed") is True


# ---------------------------------------------------------------------------
# VerifierScorer
# ---------------------------------------------------------------------------

class TestVerifierScorer:
    def test_scorer_id(self):
        assert VerifierScorer().scorer_id == "verifier"

    @pytest.mark.asyncio
    async def test_score_with_env_exec_and_read(self):
        scorer = VerifierScorer(test_command="python check.py", reward_path="/logs/reward.txt")

        async def mock_exec(cmd, **kwargs):
            return {"exit_code": 0, "timed_out": False}

        async def mock_read(path):
            return "0.85"

        ctx = _ctx(sample_metadata={
            "environment_exec": mock_exec,
            "environment_read_file": mock_read,
        })

        result = await scorer.ascore(None, {}, ctx)
        assert "verifier" in result
        assert abs(result["verifier"].value - 0.85) < 1e-9
        assert result["verifier"].metadata["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_score_no_env_handles_command_pass(self):
        scorer = VerifierScorer()
        ctx = _ctx()
        result = await scorer.ascore(None, {}, ctx)
        # No env handles — default to 0.0 (no execution)
        assert "verifier" in result
        assert result["verifier"].value == 0.0

    @pytest.mark.asyncio
    async def test_score_env_command_pass_no_file_reader(self):
        """When command passes but no file reader, assume reward=1.0."""
        scorer = VerifierScorer()

        async def mock_exec(cmd, **kwargs):
            return {"exit_code": 0, "timed_out": False}

        ctx = _ctx(sample_metadata={"environment_exec": mock_exec})
        result = await scorer.ascore(None, {}, ctx)
        assert result["verifier"].value == 1.0

    @pytest.mark.asyncio
    async def test_score_json_reward(self):
        scorer = VerifierScorer(reward_path="/logs/reward.json")

        async def mock_exec(cmd, **kwargs):
            return {"exit_code": 0, "timed_out": False}

        async def mock_read(path):
            return '{"reward": 0.95}'

        ctx = _ctx(sample_metadata={
            "environment_exec": mock_exec,
            "environment_read_file": mock_read,
        })

        result = await scorer.ascore(None, {}, ctx)
        assert abs(result["verifier"].value - 0.95) < 1e-9

    @pytest.mark.asyncio
    async def test_score_reward_read_error(self):
        scorer = VerifierScorer()

        async def mock_exec(cmd, **kwargs):
            return {"exit_code": 0, "timed_out": False}

        async def mock_read(path):
            raise FileNotFoundError("reward file not found")

        ctx = _ctx(sample_metadata={
            "environment_exec": mock_exec,
            "environment_read_file": mock_read,
        })

        result = await scorer.ascore(None, {}, ctx)
        # Default to 0.0 when reward read fails (non-strict)
        assert result["verifier"].value == 0.0
        assert "reward_read_error" in result["verifier"].metadata
