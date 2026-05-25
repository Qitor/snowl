"""Tests for separated-mode scorers and registry."""

import pytest

from snowl.core.scorer import Score, ScoreContext
from snowl.scorer.separated import (
    SeparatedCommandCheckScorer,
    SeparatedWorkspaceDiffScorer,
    SEPARATED_SCORER_REGISTRY,
    get_separated_scorer,
)
from snowl.runtime.separated_verifier import VerifierResult


def _ctx(**overrides):
    defaults = dict(task_id="t1", agent_id="a1")
    defaults.update(overrides)
    return ScoreContext(**defaults)


# ---------------------------------------------------------------------------
# SeparatedCommandCheckScorer
# ---------------------------------------------------------------------------

class TestSeparatedCommandCheckScorer:
    def test_scorer_id(self):
        assert SeparatedCommandCheckScorer.scorer_id == "command_check"

    def test_resolve_command_from_constructor(self):
        scorer = SeparatedCommandCheckScorer(command="python check.py")
        ctx = _ctx()
        assert scorer.resolve_command(ctx) == "python check.py"

    def test_resolve_command_from_metadata_verification_command(self):
        scorer = SeparatedCommandCheckScorer()
        ctx = _ctx(sample_metadata={"verification_command": "pytest test.py"})
        assert scorer.resolve_command(ctx) == "pytest test.py"

    def test_resolve_command_from_metadata_check_command(self):
        scorer = SeparatedCommandCheckScorer()
        ctx = _ctx(sample_metadata={"check_command": "make test"})
        assert scorer.resolve_command(ctx) == "make test"

    def test_resolve_command_constructor_takes_priority(self):
        scorer = SeparatedCommandCheckScorer(command="run.sh")
        ctx = _ctx(sample_metadata={"verification_command": "pytest"})
        assert scorer.resolve_command(ctx) == "run.sh"

    def test_resolve_command_none_when_empty(self):
        scorer = SeparatedCommandCheckScorer()
        ctx = _ctx()
        assert scorer.resolve_command(ctx) is None

    def test_score_from_result_pass(self):
        scorer = SeparatedCommandCheckScorer()
        result = VerifierResult(
            exit_code=0, stdout="ok", stderr="", timed_out=False, container_id="c1"
        )
        scores = scorer.score_from_result(result)
        assert scores["command_check"].value == 1.0
        assert "passed" in scores["command_check"].explanation.lower()

    def test_score_from_result_fail(self):
        scorer = SeparatedCommandCheckScorer()
        result = VerifierResult(
            exit_code=1, stdout="", stderr="error", timed_out=False, container_id="c1"
        )
        scores = scorer.score_from_result(result)
        assert scores["command_check"].value == 0.0
        assert "failed" in scores["command_check"].explanation.lower()

    def test_score_from_result_timeout(self):
        scorer = SeparatedCommandCheckScorer()
        result = VerifierResult(
            exit_code=-1, stdout="", stderr="", timed_out=True, container_id="c1"
        )
        scores = scorer.score_from_result(result)
        assert scores["command_check"].value == 0.0
        assert scores["command_check"].metadata["timed_out"] is True

    def test_score_from_result_metadata(self):
        scorer = SeparatedCommandCheckScorer()
        result = VerifierResult(
            exit_code=0, stdout="output text", stderr="", timed_out=False, container_id="c1"
        )
        scores = scorer.score_from_result(result)
        meta = scores["command_check"].metadata
        assert meta["separated"] is True
        assert meta["container_id"] == "c1"
        assert meta["exit_code"] == 0


# ---------------------------------------------------------------------------
# SeparatedWorkspaceDiffScorer
# ---------------------------------------------------------------------------

class TestSeparatedWorkspaceDiffScorer:
    def test_scorer_id(self):
        assert SeparatedWorkspaceDiffScorer.scorer_id == "workspace_diff"

    def test_resolve_command_from_metadata(self):
        scorer = SeparatedWorkspaceDiffScorer()
        ctx = _ctx(sample_metadata={"workspace_check_command": "diff -r /expected /workspace"})
        assert scorer.resolve_command(ctx) == "diff -r /expected /workspace"

    def test_resolve_command_from_expected_files(self):
        scorer = SeparatedWorkspaceDiffScorer()
        ctx = _ctx(sample_metadata={"expected_files": ["output.txt", "report.json"]})
        cmd = scorer.resolve_command(ctx)
        assert 'test -f "/workspace/output.txt"' in cmd
        assert 'test -f "/workspace/report.json"' in cmd

    def test_resolve_command_none_when_empty(self):
        scorer = SeparatedWorkspaceDiffScorer()
        ctx = _ctx()
        assert scorer.resolve_command(ctx) is None

    def test_score_from_result_pass(self):
        scorer = SeparatedWorkspaceDiffScorer()
        result = VerifierResult(
            exit_code=0, stdout="", stderr="", timed_out=False, container_id="c2"
        )
        scores = scorer.score_from_result(result)
        assert scores["workspace_diff"].value == 1.0

    def test_score_from_result_fail(self):
        scorer = SeparatedWorkspaceDiffScorer()
        result = VerifierResult(
            exit_code=1, stdout="", stderr="missing", timed_out=False, container_id="c2"
        )
        scores = scorer.score_from_result(result)
        assert scores["workspace_diff"].value == 0.0


# ---------------------------------------------------------------------------
# SEPARATED_SCORER_REGISTRY
# ---------------------------------------------------------------------------

class TestSeparatedScorerRegistry:
    def test_registry_has_command_check(self):
        assert "command_check" in SEPARATED_SCORER_REGISTRY
        assert SEPARATED_SCORER_REGISTRY["command_check"] is SeparatedCommandCheckScorer

    def test_registry_has_workspace_diff(self):
        assert "workspace_diff" in SEPARATED_SCORER_REGISTRY
        assert SEPARATED_SCORER_REGISTRY["workspace_diff"] is SeparatedWorkspaceDiffScorer

    def test_get_separated_scorer_known(self):
        cls = get_separated_scorer("command_check")
        assert cls is SeparatedCommandCheckScorer

    def test_get_separated_scorer_unknown(self):
        assert get_separated_scorer("unknown_scorer") is None