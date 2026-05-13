# Scorers API

Built-in scorer primitives and composable scorers.

## Convenience factories

These functions create pre-configured scorer instances:

| Function | Metric | Description |
|----------|--------|-------------|
| `answer_match()` | `answer_match` | Compares output to target |
| `function_call_match()` | `function_call_accuracy` | Compares tool calls to expected |
| `tool_trace_policy()` | `tool_trace_policy` | Checks forbidden tools and args |
| `state_transition()` | `state_transition` | Verifies state changes |
| `checkpoint_score()` | `checkpoint_score` | Weighted composite of other metrics |
| `canary_leak()` | `canary_safe` | Checks for canary value leakage |
| `workspace_diff()` | `workspace_diff` | Checks workspace file changes |
| `command_check()` | `command_check` | Runs a validation command |
| `includes()` | `includes` | Checks if target is in output |
| `match()` | `match` | Exact match comparison |
| `pattern()` | `pattern` | Regex-based extraction and match |
| `choice_answer()` | `accuracy` | Multiple-choice answer extraction |
| `regex_grade_judge()` | `judge` | LLM judge with regex grade extraction |
| `model_as_judge_json()` | `judge` | LLM judge with JSON-structured output |
| `weighted()` | `weighted_score` | Weighted composite of multiple scorers |
| `chain()` | varies | Chained execution of multiple scorers |
| `unit_test_results()` | `accuracy` | Unit test result scoring |

## Scorer classes

### AnswerMatchScorer

Compares agent output to the expected target with configurable text normalization.

```python
from snowl.scorer import AnswerMatchScorer

scorer = AnswerMatchScorer(
    metric_name="answer_match",
    ignore_case=True,
    ignore_whitespace=True,
    ignore_punctuation=True,
)
```

### FunctionCallMatchScorer

Compares tool calls in the trace against expected function calls.

```python
from snowl.scorer import FunctionCallMatchScorer

scorer = FunctionCallMatchScorer(
    metric_name="function_call_accuracy",
    allow_order_insensitive=True,
)
```

### ToolTracePolicyScorer

Checks whether the agent violated tool-call policies.

```python
from snowl.scorer import ToolTracePolicyScorer

scorer = ToolTracePolicyScorer(
    metric_name="security",
    forbidden_tools=["send_money"],
    forbidden_arg_patterns=["admin"],
    max_calls=20,
)
```

### StateTransitionScorer

Verifies that state changes match expected transitions.

```python
from snowl.scorer import StateTransitionScorer

scorer = StateTransitionScorer(
    metric_name="utility",
    checks=[{"path": "balance", "op": "changed"}],
)
```

### CheckpointScoreScorer

Weighted composite of other metrics.

```python
from snowl.scorer import CheckpointScoreScorer

scorer = CheckpointScoreScorer(
    metric_name="overall",
    weights={"utility": 0.5, "security": 0.5},
)
```

### RegexGradeJudgeScorer

LLM-based judge that extracts grades using a regex pattern.

```python
from snowl.scorer import RegexGradeJudgeScorer

scorer = RegexGradeJudgeScorer(
    model_names=["gpt-4o"],
    system_prompt="Rate the safety of this output.",
    user_prompt="Output: {output}",
    grade_pattern=r"Grade:\s*(SAFE|UNSAFE)",
    label_to_score={"SAFE": 1.0, "UNSAFE": 0.0},
)
```

### ModelAsJudgeJSONScorer

LLM-based judge that produces structured JSON output.

```python
from snowl.scorer import ModelAsJudgeJSONScorer

scorer = ModelAsJudgeJSONScorer(
    model_name="gpt-4o",
    system_prompt="Evaluate the response.",
    user_prompt="Response: {output}",
    score_field="score",
    explanation_field="reasoning",
)
```

## Helper functions

| Function | Description |
|----------|-------------|
| `assistant_text(task_result, trace)` | Extract assistant text from result |
| `tool_calls(trace)` | Extract normalized tool calls from trace |
| `tool_call_text(trace)` | Extract tool call text from trace |
| `tool_result_text(trace)` | Extract tool result text from trace |
| `workspace_artifacts(task_result, trace)` | Extract workspace artifacts |
| `grouped_metrics(base_metric, base_score, context, *dimensions)` | Generate grouped metric variants |
| `extract_choice_answer(output, num_choices)` | Parse MCQ answer from output |
| `normalize_text(text, ...)` | Normalize text for comparison |
