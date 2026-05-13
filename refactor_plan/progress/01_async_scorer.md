# Progress: Iteration 1 — AsyncScorer Protocol

**Status**: COMPLETED
**Date**: 2026-05-12

## What Was Completed

1. **`snowl/core/scorer.py`** — Added:
   - `AsyncScorer` protocol with `async def ascore(task_result, trace, context) -> ScoreMap`
   - `SyncScorerAdapter` class wrapping sync `Scorer` for `AsyncScorer` compatibility
   - `is_async_scorer()` helper (checks `hasattr(scorer, 'ascore')`)
   - `validate_async_scorer()` function

2. **`snowl/runtime/engine.py`** — Modified `score_trial_phase` (~line 1013):
   - Conditional dispatch: `ascore()` for async scorers, `asyncio.to_thread(score)` for sync
   - Fully backward compatible — all existing sync scorers work unchanged

3. **`snowl/scorer/model_judge.py`** — Added `async def ascore()` to `ModelAsJudgeJSONScorer`:
   - Calls `await client.generate()` directly instead of `_run_coro_sync()` hack
   - Can participate in provider admission for judge model API calls
   - Existing `score()` method preserved for backward compatibility

4. **`snowl/core/__init__.py`** — Updated exports:
   - Added `AsyncScorer`, `SyncScorerAdapter`, `is_async_scorer`, `validate_async_scorer`

5. **`tests/test_async_scorer_protocol.py`** — 11 new tests:
   - SyncScorerAdapter wrapping and scorer_id preservation
   - is_async_scorer detection for async-only, sync-only, dual, and plain objects
   - validate_async_scorer for valid, missing_id, and missing_ascore cases
   - Integration test: score_trial_phase dispatches to ascore for async scorers

## Test Results

- 356 passed, 1 skipped (pre-existing)
- 2 pre-existing failures in test_eval_web_observability.py (Node.js environment issue, unrelated)

## Deviations from Plan

- None. All planned changes implemented as specified.

## Known Issues / Follow-up Items

- The `ModelAsJudgeJSONScorer.ascore()` does not yet acquire `provider_admission` — that requires passing the scheduler into the scorer context, which will be addressed when `BenchmarkConcurrencyProfile` (Iteration 2) adds `scorer_uses_provider` integration.
- The `_run_coro_sync` function in model_judge.py is still used by `score()` — it can be removed in a future cleanup once all callers migrate to `ascore()`.

## Next Iteration

**Iteration 2: BenchmarkConcurrencyProfile** — Add benchmark-specific concurrency profiles to RuntimePolicy, including scorer provider budget integration for ToolEmu and AgentDojo.
