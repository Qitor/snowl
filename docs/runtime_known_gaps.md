# Runtime Known Gaps

Snowl's runtime is useful and test-backed, but still transitional. The repo already has real multi-budget throttling and a coarse execute/score split, yet several exposed runtime surfaces are not fully wired into the main eval loop.

## Confirmed Current Mismatches

| Gap | What exists now | What is missing | Future changes must not assume |
| --- | --- | --- | --- |
| Finalize in repo-level eval | `finalize_trial_phase()` exists and `execute_trial()` uses it. | `_run_one()` in `snowl/eval.py` does not call it. | Repo-level evals currently do not guarantee finalize-phase teardown/event behavior just because the engine helper exists. |
| Prepare as an independent phase | `prepare_trial_phase()` is a real helper in `snowl/runtime/engine.py`. | Main eval dispatch does not admit prepare separately; it happens inside `execute_agent_phase(request)` under `running_trial_slot()`. | Prepare is not independently scheduled today. |
| Provider-aware scheduling | Provider budgets are real and model calls acquire provider slots through `OpenAICompatibleChatClient`. | Dispatch order does not use provider headroom to choose the next trial. | Provider budgets do not yet mean provider-aware queue prioritization. |
| `spec_hash` locality | TerminalBench and OSWorld providers compute `spec_hash`, and payload/trace can record it. | Queue order does not change based on `spec_hash`; there is no batching or locality preference. | `spec_hash` is metadata today, not a dispatch policy input. |
| Plan-aware runtime objects | `TaskExecutionPlan`, `TrialDescriptor`, `TrialRequest.execution_plan`, and `TrialRequest.trial_descriptor` exist. | Repo-level eval does not populate or consume them for scheduling. | Exposed planning objects are not proof of plan-aware scheduling. |
| Prepare/finalize scheduler APIs | `begin_prepare()` and `begin_finalize()` exist on `ResourceScheduler`. | The main eval loop uses only running and scoring slots directly. | A phase API existing in the scheduler does not mean the eval loop uses it. |
| Container slot enforcement | `max_container_slots` exists, is tracked, and wraps sandbox runtimes. | It is not a universal admission gate across all benchmark container prepare paths. | Every container-backed path is not centrally governed by the same slot today. |
| Phase-aware retry | Deferred whole-trial auto retry and provider HTTP retry are real. | Prepare, score, and finalize are not retried as separately scheduled phases. | Retry policy is not phase-specific today. |

## Suspected But Not Fully Confirmed Ambiguities

These are grounded suspicions from code reading, but they still deserve benchmark-specific confirmation before hardening them into stronger claims.

| Ambiguity | What exists now | What is unclear | Future changes must not assume |
| --- | --- | --- | --- |
| Operational impact of skipped finalize | The main eval loop skips `finalize_trial_phase()`. | The exact cleanup impact may vary by benchmark/provider path and by current local environment behavior. | That missing finalize is harmless for every benchmark. |
| Scope of `max_container_slots` in real benchmark runs | Sandbox wrapping is clearly gated. Container providers have their own prepare paths. | The precise end-to-end throttling effect should be validated benchmark-by-benchmark, especially for TerminalBench and OSWorld. | A control appearing in profiling means it governed the exact path you changed. |
| Reusability of planning hooks by external callers | `TrialRequest` can carry execution-plan metadata. | Repo-level docs should not imply external callers are already using those hooks in a stable way. | Adding metadata fields automatically changes runtime behavior. |

## Forward-Looking Areas Documented Elsewhere But Not Yet Implemented

- `docs/runtime_scheduling.md`
- `docs/runtime_scheduling_v2.md`

These documents describe intended runtime evolution, including:

- independently scheduled prepare/execute/score/finalize phases
- locality-aware dispatch using `spec_hash`
- stronger provider-aware dispatch
- richer retry semantics
- deeper container pooling and reuse

Those are design directions, not current contracts.

## Practical Reading Rule

For runtime tasks, read in this order:

1. `snowl/eval.py`
2. `snowl/runtime/engine.py`
3. `snowl/runtime/resource_scheduler.py`
4. focused tests
5. `docs/current_state.md`
6. this file
7. forward-looking runtime design docs only after the code path is clear
