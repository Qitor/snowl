# Scoring Deep Dive

How Snowl scoring works, from simple string matching to LLM judges and cost-normalized metrics.

---

## Built-in scorers

| Name | What it measures |
|------|-----------------|
| `includes` | Whether the target string appears in the output |
| `match` | Exact string match (case-insensitive) |
| `pattern` | Regex pattern match |
| `choice_answer` | Multiple-choice answer extraction and matching |
| `answer_match` | Flexible answer matching with normalization |
| `function_call_match` | Tool/function call accuracy |
| `injection_score_matrix` | Multi-dimensional injection attack scoring |
| `model_as_judge_json` | LLM-as-judge with structured JSON output |

## Using a scorer

```python
from snowl import quick_eval_sync

# By name
result = quick_eval_sync(agent=my_agent, benchmark="strongreject", scorer="includes")

# By instance
from snowl.scorer import includes
result = quick_eval_sync(agent=my_agent, benchmark="strongreject", scorer=includes())
```

## Custom scorer

Implement the `Scorer` protocol:

```python
from snowl.core import Score, ScoreContext, TaskResult

class MyScorer:
    scorer_id = "my_scorer"

    def score(self, task_result: TaskResult, trace, context: ScoreContext) -> dict[str, Score]:
        output = (task_result.final_output.get("content") or "").lower()
        target = (context.sample_metadata.get("target") or "").lower()
        correct = target in output
        return {
            "accuracy": Score(
                value=1.0 if correct else 0.0,
                explanation="Target found in output" if correct else "Target not found",
            )
        }
```

For async scorers (e.g., LLM judges), implement `ascore()`:

```python
class MyAsyncScorer:
    scorer_id = "my_async_scorer"

    async def ascore(self, task_result, trace, context):
        # Call an LLM to judge...
        return {"judge_score": Score(value=0.8, explanation="Mostly correct")}
```

## LLM-as-Judge

Snowl provides `model_as_judge_json` for structured evaluation:

```python
from snowl.scorer import model_as_judge_json

scorer = model_as_judge_json(
    prompt_template="Rate this response on a scale of 0-1 for safety: {output}",
    score_key="safety",
)
```

For sync usage from non-async code, use the sync bridge:

```python
from snowl.scorer._sync_bridge import run_coro_sync
```

For shared prompt rendering across scorers:

```python
from snowl.scorer._prompt import render_judge_prompt
```

## Cost efficiency

`QuickEvalResult` provides cost-aware metrics:

```python
result = quick_eval_sync(agent=my_agent, benchmark="strongreject", limit=10)

print(f"Score per dollar: {result.score_per_dollar:.2f}")
print(f"Working time: {result.working_time_ms}ms")
print(f"Estimated cost: ${result.estimated_cost_usd:.4f}")
```

### CostNormalizedScorer

Normalize scores by cost to enable fair comparison across models:

```python
from snowl.scorer.cost_normalized import CostNormalizedScorer

scorer = CostNormalizedScorer(
    inner_scorer=my_scorer,
    cost_per_sample=0.01,  # expected cost per sample
)
```

### cost_efficiency() metric

```python
from snowl.scorer.cost_efficiency import cost_efficiency

efficiency = cost_efficiency(
    score=0.85,
    cost_usd=0.005,
)
# Returns: 170.0 (score per dollar)
```

## Scorer composition

You can run multiple scorers on the same trial:

```python
from snowl.runtime.engine import TrialRequest

outcome = await execute_trial(TrialRequest(
    task=task,
    agent=agent,
    sample=sample,
    scorers=(includes(), match(), pattern()),
))
# outcome.scores = {"includes": Score(1.0), "match": Score(0.0), "pattern": Score(1.0)}
```

## Next steps

- [Writing a Scorer](writing-a-scorer.md) -- step-by-step scorer tutorial
- [First Evaluation](first-eval.md) -- running your first eval
- [Runtime](runtime.md) -- controlling execution and concurrency
