"""Tests for ScoreReducer protocol and built-in implementations."""

import math
import pytest

from snowl.core.scorer import Score
from snowl.core.reducer import (
    MeanReducer,
    MaxReducer,
    PassAtKReducer,
    ScoreReducer,
    _compute_pass_at_k,
    resolve_score_reducer,
    validate_score_reducer,
)
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# MeanReducer
# ---------------------------------------------------------------------------

class TestMeanReducer:
    def test_reducer_id(self):
        assert MeanReducer.reducer_id == "mean"

    def test_protocol_conformance(self):
        r = MeanReducer()
        assert isinstance(r, ScoreReducer)

    def test_mean_of_scores(self):
        r = MeanReducer()
        scores = [
            {"accuracy": Score(value=1.0)},
            {"accuracy": Score(value=0.0)},
            {"accuracy": Score(value=1.0)},
        ]
        result = r.reduce(scores)
        assert abs(result["accuracy"].value - 2 / 3) < 1e-9

    def test_mean_single_epoch(self):
        r = MeanReducer()
        scores = [{"accuracy": Score(value=0.8)}]
        result = r.reduce(scores)
        assert result["accuracy"].value == 0.8

    def test_empty_input(self):
        r = MeanReducer()
        assert r.reduce([]) == {}

    def test_multiple_metrics(self):
        r = MeanReducer()
        scores = [
            {"a": Score(value=1.0), "b": Score(value=0.5)},
            {"a": Score(value=0.0), "b": Score(value=1.0)},
        ]
        result = r.reduce(scores)
        assert result["a"].value == 0.5
        assert result["b"].value == 0.75

    def test_metadata(self):
        r = MeanReducer()
        scores = [{"a": Score(value=1.0)}, {"a": Score(value=0.0)}]
        result = r.reduce(scores)
        assert result["a"].metadata["epochs"] == 2
        assert result["a"].metadata["values"] == [1.0, 0.0]


# ---------------------------------------------------------------------------
# MaxReducer
# ---------------------------------------------------------------------------

class TestMaxReducer:
    def test_reducer_id(self):
        assert MaxReducer.reducer_id == "max"

    def test_protocol_conformance(self):
        assert isinstance(MaxReducer(), ScoreReducer)

    def test_max_of_scores(self):
        r = MaxReducer()
        scores = [
            {"accuracy": Score(value=0.0)},
            {"accuracy": Score(value=0.5)},
            {"accuracy": Score(value=1.0)},
        ]
        result = r.reduce(scores)
        assert result["accuracy"].value == 1.0

    def test_empty_input(self):
        assert MaxReducer().reduce([]) == {}


# ---------------------------------------------------------------------------
# PassAtKReducer
# ---------------------------------------------------------------------------

class TestPassAtKReducer:
    def test_reducer_id(self):
        assert PassAtKReducer(k=1).reducer_id == "pass_at_k"

    def test_protocol_conformance(self):
        assert isinstance(PassAtKReducer(k=1), ScoreReducer)

    def test_k_validation(self):
        with pytest.raises(ValueError, match="k >= 1"):
            PassAtKReducer(k=0)

    def test_all_correct_pass_at_1(self):
        r = PassAtKReducer(k=1)
        scores = [{"a": Score(value=1.0)}, {"a": Score(value=1.0)}, {"a": Score(value=1.0)}]
        result = r.reduce(scores)
        assert result["a"].value == 1.0

    def test_none_correct_pass_at_1(self):
        r = PassAtKReducer(k=1)
        scores = [{"a": Score(value=0.0)}, {"a": Score(value=0.0)}, {"a": Score(value=0.0)}]
        result = r.reduce(scores)
        assert result["a"].value == 0.0

    def test_two_correct_of_three_pass_at_1(self):
        r = PassAtKReducer(k=1)
        scores = [
            {"a": Score(value=1.0)},
            {"a": Score(value=0.0)},
            {"a": Score(value=1.0)},
        ]
        result = r.reduce(scores)
        # pass@1 = 1 - C(1,1)/C(3,1) = 1 - 1/3 = 2/3
        assert abs(result["a"].value - 2 / 3) < 1e-9

    def test_pass_at_2(self):
        r = PassAtKReducer(k=2)
        scores = [
            {"a": Score(value=1.0)},
            {"a": Score(value=0.0)},
            {"a": Score(value=0.0)},
        ]
        result = r.reduce(scores)
        # pass@2 = 1 - C(2,2)/C(3,2) = 1 - 1/3 = 2/3
        assert abs(result["a"].value - 2 / 3) < 1e-9

    def test_pass_at_k_all_correct(self):
        r = PassAtKReducer(k=2)
        scores = [{"a": Score(value=1.0)}, {"a": Score(value=1.0)}]
        result = r.reduce(scores)
        # n-c = 0 < k => pass@k = 1.0
        assert result["a"].value == 1.0

    def test_empty_input(self):
        r = PassAtKReducer(k=1)
        assert r.reduce([]) == {}

    def test_metadata(self):
        r = PassAtKReducer(k=1)
        scores = [{"a": Score(value=1.0)}, {"a": Score(value=0.0)}]
        result = r.reduce(scores)
        meta = result["a"].metadata
        assert meta["n"] == 2
        assert meta["c"] == 1
        assert meta["k"] == 1


# ---------------------------------------------------------------------------
# _compute_pass_at_k
# ---------------------------------------------------------------------------

class TestComputePassAtK:
    def test_all_correct(self):
        assert _compute_pass_at_k(n=3, c=3, k=2) == 1.0

    def test_none_correct(self):
        assert _compute_pass_at_k(n=3, c=0, k=1) == 0.0

    def test_one_correct_of_ten_pass_at_1(self):
        # pass@1 = 1 - C(9,1)/C(10,1) = 1 - 9/10 = 0.1
        assert abs(_compute_pass_at_k(n=10, c=1, k=1) - 0.1) < 1e-9

    def test_large_n_no_overflow(self):
        # Should not overflow for large n
        result = _compute_pass_at_k(n=1000, c=500, k=10)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# validate_score_reducer
# ---------------------------------------------------------------------------

class TestValidateScoreReducer:
    def test_valid_reducer(self):
        validate_score_reducer(MeanReducer())  # no error

    def test_missing_reducer_id(self):
        class Bad:
            def reduce(self, scores): return {}
        with pytest.raises(SnowlValidationError, match="reducer_id"):
            validate_score_reducer(Bad())

    def test_missing_reduce(self):
        class Bad:
            reducer_id = "bad"
        with pytest.raises(SnowlValidationError, match="reduce"):
            validate_score_reducer(Bad())


# ---------------------------------------------------------------------------
# resolve_score_reducer
# ---------------------------------------------------------------------------

class TestResolveScoreReducer:
    def test_epochs_1_returns_none(self):
        assert resolve_score_reducer("mean", epochs=1) is None

    def test_mean(self):
        r = resolve_score_reducer("mean", epochs=3)
        assert isinstance(r, MeanReducer)

    def test_max(self):
        r = resolve_score_reducer("max", epochs=2)
        assert isinstance(r, MaxReducer)

    def test_pass_at_k(self):
        r = resolve_score_reducer("pass_at_k", epochs=5)
        assert isinstance(r, PassAtKReducer)
        assert r.k == 5

    def test_pass_at_k_custom_k(self):
        r = resolve_score_reducer("pass_at_k", epochs=5, k=1)
        assert isinstance(r, PassAtKReducer)
        assert r.k == 1

    def test_unknown_rejected(self):
        with pytest.raises(SnowlValidationError, match="Unknown"):
            resolve_score_reducer("unknown", epochs=3)
