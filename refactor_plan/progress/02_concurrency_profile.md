# Progress: Iteration 2 — BenchmarkConcurrencyProfile

**Status**: COMPLETED
**Date**: 2026-05-12

## What Was Completed

1. **`snowl/benchmarks/base.py`** — Added:
   - `BenchmarkConcurrencyProfile` dataclass with fields: `name`, `api_call_amplification`, `recommended_max_running`, `scorer_uses_provider`, `scorer_provider_id`, `recommended_scoring_tasks`
   - `concurrency_profile` field (default `None`) on `BenchmarkInfo`

2. **`snowl/runtime/policy.py`** — Added:
   - `_get_benchmark_profile()` helper that looks up profile from the registry based on task benchmark metadata
   - In `resolve()`: applies `recommended_max_running` (when no explicit override and not docker-like), applies `recommended_scoring_tasks` (when no explicit override), adds scorer provider to `provider_budget_map` when `scorer_uses_provider=True`

3. **`snowl/benchmarks/registry.py`** — Registered profiles:
   - ToolEmu: `api_call_amplification=30.0, recommended_max_running=3, scorer_uses_provider=True, scorer_provider_id="openai"`
   - AgentDojo: `api_call_amplification=5.0, recommended_max_running=6`

4. **`tests/test_benchmark_concurrency_profile.py`** — 13 new tests:
   - Profile creation, defaults, custom values
   - BenchmarkInfo with/without profile
   - _get_benchmark_profile for toolemu, agentdojo, mixed, unknown, empty
   - RuntimePolicy integration: profile applied, explicit override wins, scorer provider budget added, no change for benchmarks without profiles

## Test Results

- 369 passed, 1 skipped
- No regressions

## Deviations from Plan

- None. All planned changes implemented as specified.

## Known Issues / Follow-up Items

- The `api_call_amplification` field is informational only — it's not yet used to dynamically adjust provider budgets. Future work could use it to compute `provider_budget = floor(total_budget / amplification)`.
- Docker-like benchmarks are explicitly excluded from profile-based max_running reduction (the existing serial heuristic takes precedence).

## Next Iteration

**Iteration 3: ToolMiddleware Protocol + ReActAgent Integration** — Introduce ToolMiddleware protocol and wire into ReActAgent._execute_tool_call.
