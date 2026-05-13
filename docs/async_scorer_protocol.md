# Async Scorer Protocol

## Overview

The `AsyncScorer` protocol enables native-async scoring for evaluators that need to make asynchronous model API calls (e.g., LLM-as-judge). This is critical for benchmarks like ToolEmu that use LM-based trajectory evaluation, and for any future LLM-judge scoring workflow.

## Protocol Definition

```python
class AsyncScorer(Protocol):
    scorer_id: str

    async def ascore(
        self,
        task_result: TaskResult,
        trace: Trace,
        context: ScoreContext,
    ) -> ScoreMap: ...
```

## Relationship to Sync Scorer

The existing `Scorer` protocol (with `score()`) is unchanged and fully backward compatible. The runtime automatically detects which protocol a scorer implements:

- **Has `ascore()`**: Runtime calls `await scorer.ascore()` directly in the async event loop
- **Only has `score()`**: Runtime calls `await asyncio.to_thread(scorer.score, ...)` (same as before)

A scorer can implement both `score()` and `ascore()` for dual compatibility.

## Wrapping Sync Scorers

If you need to pass a sync scorer where an `AsyncScorer` is expected, use `SyncScorerAdapter`:

```python
from snowl.core import SyncScorerAdapter

sync_scorer = MySyncScorer()
async_scorer = SyncScorerAdapter(sync_scorer)
# async_scorer.ascore() delegates to asyncio.to_thread(sync_scorer.score, ...)
```

## Detection Helper

```python
from snowl.core import is_async_scorer

if is_async_scorer(my_scorer):
    # Has ascore() — can participate in provider admission
else:
    # Only has score() — runs via thread pool
```

## Why Async Scoring Matters

1. **Provider admission**: Async scorers can acquire `provider_admission` slots from the `ResourceScheduler`, ensuring judge model calls respect rate limits and concurrency budgets.
2. **No thread shims**: The `ModelAsJudgeJSONScorer` previously used `_run_coro_sync()` — a hack that spawned a new thread with its own event loop. With `ascore()`, the judge call runs natively in the main event loop.
3. **Scoring slot efficiency**: Sync scorers occupy a scoring slot for the entire duration (including idle time during API waits). Async scorers release the event loop during API waits, allowing other work to proceed.

## Example: Implementing an Async Scorer

```python
from snowl.core import Score, ScoreContext, TaskResult

class MyLLMJudgeScorer:
    scorer_id = "my_llm_judge"

    async def ascore(self, task_result, trace, context):
        # Make an async model call
        response = await self.client.generate(
            messages=[{"role": "user", "content": "Evaluate this..."}],
            model=self.model_name,
        )
        score_value = float(self._parse_response(response))
        return {
            "judge_score": Score(
                value=score_value,
                explanation="LLM-judged score",
                metadata={"judge_model": self.model_name},
            )
        }
```

## Migration Guide

To migrate an existing sync scorer to async:

1. Add an `async def ascore(self, task_result, trace, context) -> ScoreMap` method
2. Replace any `_run_coro_sync(client.generate(...))` calls with `await client.generate(...)`
3. Keep the existing `score()` method for backward compatibility (optional but recommended)
4. The runtime will automatically prefer `ascore()` when available
