# Runtime & Scheduler

Detailed reference for Snowl's runtime architecture and resource scheduling.

---

## Control plane vs execution plane

### Control plane

The control plane decides what work exists, how much work may run, and how run
state is persisted.

Main responsibilities:

- Project loading and component discovery in `snowl/eval.py`
- Plan expansion into `PlanTrial`s
- Runtime budget resolution
- Queue dispatch, retry queue handling, and in-flight limits
- Artifact bootstrap and final artifact writing
- Recovery ledger updates
- Runtime-state heartbeats and event persistence

If a change affects queue order, resource admission, retry scheduling, artifact
status, or run lifecycle, start by reading `snowl/eval.py`.

### Execution plane

The execution plane performs the work of one trial once it has been dispatched.

Main responsibilities:

- `prepare_trial_phase()`, `execute_agent_phase()`, `score_trial_phase()`,
  `finalize_trial_phase()` in `snowl/runtime/engine.py`
- Task-declared container resolution in `snowl/runtime/container_runtime.py`
- Sandbox and environment operations in `snowl/envs/`
- Model-call behavior and per-request retries in
  `snowl/model/openai_compatible.py`

---

## Task-declared container contract

Snowl treats container-backed work as a three-layer contract:

1. **Task/sample metadata** declares whether the trial needs a runtime-managed
   container under `runtime_container`
2. **Runtime/engine** resolves that metadata into a `RuntimeContainerSpec`,
   creates the provider session, registers the resource, leases it to the
   trial, and owns release/cleanup
3. **Agents** consume only the injected `__snowl_container_session`; they must
   not start or stop containers themselves

---

## Resource budget details

### max_running_trials

Enforced directly through `scheduler.running_trial_slot()`. Currently covers
the coroutine that includes both prepare and execute work.

### max_scoring_tasks

Enforced through `scheduler.scoring_slot()`. Lets scoring overlap with other
trial execution instead of blocking the main running-trial quota.

### provider_budgets

Enforced by `OpenAICompatibleChatClient` through the scheduler slot resolver.
Applies to any model call that uses the same `provider_id`. Agent calls and
judge calls share the same budget.

### max_builds

Exposed by `scheduler.build_slot()`. Used by compose-build paths.

### max_container_slots

Gates runtime-managed container prepare through `begin_prepare()` and sandbox
runtimes through the scheduled sandbox wrapper.

---

## Current dispatch behavior

The runtime is close to FIFO in several ways:

- `fresh_queue` is drained in plan order with `pop(0)`
- `recovery_queue` dispatches the first ready retry item
- No fairness or locality policy beyond queue order
- `TaskExecutionPlan.priority` and `TrialDescriptor.phase` are not yet driving
  dispatch

Mental model: Snowl has multi-budget throttling and a coarse execute/score
split, but not a mature phase-aware dispatcher yet.

---

## Where scheduling is still shallow

- Prepare is not a fully separate worker pool
- Provider headroom is visible but not used for dispatch prioritization
- `spec_hash` is computed but not used for batching or locality
- Finalize has no dedicated concurrency limit
- Phase-level retry is not implemented
