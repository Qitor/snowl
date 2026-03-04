"""Built-in scorer library."""

from snowl.scorer.base import (
    OutputExtractor,
    TargetExtractor,
    default_output_extractor,
    default_target_extractor,
    normalize_text,
)
from snowl.scorer.composition import ChainedScorer, WeightedCompositeScorer, chain, weighted
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
    "ModelAsJudgeJSONScorer",
    "OutputExtractor",
    "PatternScorer",
    "WeightedCompositeScorer",
    "UnitTestResultScorer",
    "UnitTestStatus",
    "TargetExtractor",
    "default_output_extractor",
    "default_target_extractor",
    "includes",
    "match",
    "model_as_judge_json",
    "normalize_text",
    "parse_pytest_summary",
    "pattern",
    "chain",
    "weighted",
    "unit_test_results",
]
