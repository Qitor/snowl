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
from snowl.scorer.agent import (
    AnswerMatchScorer,
    CanaryLeakScorer,
    CheckpointScoreScorer,
    CommandCheckScorer,
    FunctionCallMatchScorer,
    InjectionScoreMatrix,
    StateTransitionScorer,
    ToolTracePolicyScorer,
    WorkspaceDiffScorer,
    answer_match,
    canary_leak,
    checkpoint_score,
    command_check,
    function_call_match,
    grouped_metrics,
    injection_score_matrix,
    judge_rubric,
    state_transition,
    tool_trace_policy,
    workspace_diff,
)
from snowl.scorer.composition import ChainedScorer, WeightedCompositeScorer, chain, weighted
from snowl.scorer.choice import ChoiceAnswerScorer, choice_answer, extract_choice_answer, normalize_choice_targets
from snowl.scorer.grade_judge import JudgeClientFactory, MultiJudgeReducer, RegexGradeJudgeScorer, regex_grade_judge
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
from snowl.scorer.trace import (
    NormalizedToolCall,
    assistant_text,
    tool_call_text,
    tool_calls,
    tool_result_text,
    workspace_artifacts,
)

__all__ = [
    "AnswerMatchScorer",
    "CanaryLeakScorer",
    "CheckpointScoreScorer",
    "CommandCheckScorer",
    "FunctionCallMatchScorer",
    "IncludesScorer",
    "InjectionScoreMatrix",
    "JudgeClientFactory",
    "MatchScorer",
    "ChainedScorer",
    "ChoiceAnswerScorer",
    "ModelAsJudgeJSONScorer",
    "MultiJudgeReducer",
    "NormalizedToolCall",
    "OutputExtractor",
    "PatternScorer",
    "RegexGradeJudgeScorer",
    "StateTransitionScorer",
    "ToolTracePolicyScorer",
    "WeightedCompositeScorer",
    "WorkspaceDiffScorer",
    "UnitTestResultScorer",
    "UnitTestStatus",
    "TargetExtractor",
    "default_output_extractor",
    "default_target_extractor",
    "answer_match",
    "assistant_text",
    "canary_leak",
    "checkpoint_score",
    "choice_answer",
    "command_check",
    "function_call_match",
    "grouped_metrics",
    "includes",
    "injection_score_matrix",
    "judge_rubric",
    "match",
    "model_as_judge_json",
    "normalize_text",
    "extract_choice_answer",
    "normalize_choice_targets",
    "parse_pytest_summary",
    "pattern",
    "chain",
    "regex_grade_judge",
    "state_transition",
    "tool_call_text",
    "tool_calls",
    "tool_result_text",
    "tool_trace_policy",
    "weighted",
    "workspace_artifacts",
    "workspace_diff",
    "unit_test_results",
]
