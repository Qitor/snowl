# Runtime Known Gaps

Snowl's runtime now has task-declared, runtime-owned container lifecycle management for TerminalBench and OSWorld, plus a run-end cleanup barrier. It is still transitional in scheduling depth and broader container standardization.

## Confirmed Current Mismatches

| Gap | What exists now | What is missing | Future changes must not assume |
| --- | --- | --- | --- |
| Prepare as an independent phase | `prepare_trial_phase()` is a real helper in `snowl/runtime/engine.py`, and repo-level eval now calls it directly. | Main eval dispatch still admits prepare while the trial is already holding `running_trial_slot()`. | Prepare is not independently scheduled today. |
| Provider-aware scheduling | Provider budgets are real and model calls acquire provider slots through `OpenAICompatibleChatClient`. | Dispatch order does not use provider headroom to choose the next trial. | Provider budgets do not yet mean provider-aware queue prioritization. |
| `spec_hash` locality | TerminalBench and OSWorld providers compute `spec_hash` from the normalized container contract, and payload/trace can record it. | Queue order does not change based on `spec_hash`; there is no batching or locality preference. | `spec_hash` is metadata today, not a dispatch policy input. |
| Plan-aware runtime objects | `TaskExecutionPlan`, `TrialDescriptor`, `TrialRequest.execution_plan`, and `TrialRequest.trial_descriptor` exist. | Repo-level eval does not populate or consume them for scheduling. | Exposed planning objects are not proof of plan-aware scheduling. |
| Prepare/finalize scheduler APIs | `begin_prepare()` and `begin_finalize()` exist on `ResourceScheduler`. | The main eval loop uses only running and scoring slots directly. | A phase API existing in the scheduler does not mean the eval loop uses it. |
| Container slot enforcement | `max_container_slots` exists, is tracked, and wraps sandbox runtimes. Runtime-owned cleanup now covers TerminalBench and OSWorld resources. | It is still not a universal admission gate across all benchmark container prepare paths. | Every container-backed path is centrally governed by the same slot today. |
| Benchmark container reuse | Runtime registers, leases, releases, and tears down standardized benchmark containers. | Runtime does not keep benchmark containers warm by default or reuse them by `spec_hash`. | Registration plus `spec_hash` means a warm pool already exists. |
| Phase-aware retry | Deferred whole-trial auto retry and provider HTTP retry are real. | Prepare, score, and finalize are not retried as separately scheduled phases. | Retry policy is not phase-specific today. |
| Task-declared container contract adoption | TerminalBench and OSWorld tasks/examples now declare `runtime_container`, and agents reject missing runtime-managed sessions. | Other future container-backed benchmarks still need to adopt the same contract explicitly. | Any container-backed benchmark automatically participates in runtime ownership without adding the contract metadata. |

## Suspected But Not Fully Confirmed Ambiguities

These are grounded suspicions from code reading, but they still deserve benchmark-specific confirmation before hardening them into stronger claims.

| Ambiguity | What exists now | What is unclear | Future changes must not assume |
| --- | --- | --- | --- |
| Scope of `max_container_slots` in real benchmark runs | Sandbox wrapping is clearly gated. Container providers have their own prepare paths. | The precise end-to-end throttling effect should be validated benchmark-by-benchmark, especially for TerminalBench and OSWorld. | A control appearing in profiling means it governed the exact path you changed. |
| How much legacy raw metadata still matters | Runtime ownership now resolves from `runtime_container`, and agents should not infer ownership from raw compose or OSWorld settings. | Some benchmark helpers and diagnostics still mirror raw metadata alongside the normalized contract. | Removing or changing those raw fields is harmless without checking the benchmark path. |
| Cleanup durability after hard process death | Run-end cleanup barrier now exists and interrupted tasks use best-effort cleanup. | A process killed hard enough may still leave resources behind until a future janitor exists. | Run-end cleanup means stale resources can never survive a crash or kill -9. |
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
