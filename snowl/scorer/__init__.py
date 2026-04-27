"""Scorer package export surface for built-in scoring primitives and factories.

Framework role:
- Aggregates text/model-judge/test-result scorers and composition utilities for benchmark and custom workflows.

Runtime/usage wiring:
- Imported by user scorers, benchmark integrations, and examples.

Change guardrails:
- Keep scorer factory names stable; they are frequently referenced in project code and docs.
"""

from snowl.scorer.base import (
    OutputExtractor,
    TargetExtractor,
    default_output_extractor,
    default_target_extractor,
    normalize_text,
)
from snowl.scorer.composition import ChainedScorer, WeightedCompositeScorer, chain, weighted
from snowl.scorer.choice import ChoiceAnswerScorer, choice_answer, extract_choice_answer, normalize_choice_targets
from snowl.scorer.grade_judge import MultiJudgeReducer, RegexGradeJudgeScorer, regex_grade_judge
from snowl.scorer.model_judge import ModelAsJudgeJSONScorer, model_as_judge_json
from snowl.scorer.test_results import (
    UnitTestResultScorer,
    UnitTestStatus,
    parse_pytest_summary,
    unit_test_results,
)
from snowl.scorer.text import (
    IncludesScorer,
    MatchScorer,
    PatternScorer,
    includes,
    match,
    pattern,
)

__all__ = [
    "IncludesScorer",
    "MatchScorer",
    "ChainedScorer",
    "ChoiceAnswerScorer",
    "ModelAsJudgeJSONScorer",
    "MultiJudgeReducer",
    "OutputExtractor",
    "PatternScorer",
    "RegexGradeJudgeScorer",
    "WeightedCompositeScorer",
    "UnitTestResultScorer",
    "UnitTestStatus",
    "TargetExtractor",
    "default_output_extractor",
    "default_target_extractor",
    "choice_answer",
    "includes",
    "match",
    "model_as_judge_json",
    "normalize_text",
    "extract_choice_answer",
    "normalize_choice_targets",
    "parse_pytest_summary",
    "pattern",
    "chain",
    "regex_grade_judge",
    "weighted",
    "unit_test_results",
]
