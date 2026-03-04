from __future__ import annotations

import pytest

from snowl.core import (
    Score,
    ScoreContext,
    TaskResult,
    TaskStatus,
    validate_scorer,
    validate_scores,
)
from snowl.errors import SnowlValidationError


class GoodScorer:
    scorer_id = "default-scorer"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {
            "accuracy": Score(value=1.0),
            "latency_score": Score(value=0.8, explanation="fast enough"),
        }


class BadScorerNoId:
    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=1.0)}


class BadScorerNoFunc:
    scorer_id = "bad"


def test_validate_scorer_ok() -> None:
    validate_scorer(GoodScorer())


def test_validate_scorer_missing_id() -> None:
    with pytest.raises(SnowlValidationError, match="scorer_id"):
        validate_scorer(BadScorerNoId())


def test_validate_scorer_missing_score() -> None:
    with pytest.raises(SnowlValidationError, match="score"):
        validate_scorer(BadScorerNoFunc())


def test_validate_scores_accepts_multiple_metrics() -> None:
    scores = {
        "accuracy": Score(value=1.0),
        "cost_efficiency": Score(value=0.6),
    }
    validate_scores(scores)


def test_validate_scores_rejects_empty() -> None:
    with pytest.raises(SnowlValidationError, match="no metrics"):
        validate_scores({})


def test_validate_scores_rejects_non_score_value() -> None:
    with pytest.raises(SnowlValidationError, match="Score instance"):
        validate_scores({"accuracy": 1.0})  # type: ignore[arg-type]
