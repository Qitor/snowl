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

## Adaptive provider flow control (AIMD)

As of v0.4, the `ResourceScheduler` implements TCP-like AIMD congestion control
per provider endpoint:

- **Multiplicative decrease on 429**: when a model call returns HTTP 429, the
  scheduler halves that provider's concurrency limit (floor, min 1).
- **Additive increase after success window**: after N consecutive successes
  (where N = current limit), the scheduler increments the limit by 1.
- **`Retry-After` parsing**: the model client extracts `Retry-After` headers
  from 429 responses and uses them as the backoff floor.

This feedback loop means the scheduler self-tunes to each endpoint's actual
rate limit without manual `provider_budgets` configuration.

Key APIs on `ResourceScheduler`:

- `report_429(provider_id)` — called from the model client when a 429 is received
- `report_success(provider_id)` — called on successful model calls
- `resize_provider_budget(provider_id, new_limit)` — resizes the provider semaphore
- `flow_state_snapshot()` — returns diagnostics for all active flow states

The model client hooks are installed at dispatch time via
`OpenAICompatibleChatClient.set_global_429_reporter()` and
`set_global_success_reporter()`.

---

## Per-endpoint provider budgeting

When a model entry in `agent_matrix.models` specifies a `provider` override
with a different `base_url` from the global provider, `project_config.py`
generates a unique `provider_id` using `_derive_endpoint_provider_id()`:

```python
provider_id = f"{parent_id}__{slug}"
# Example: inf__o8kjqm58o8ogcm5ek8aggddkb5ggk8dp
```

The slug is the first subdomain segment of the override `base_url`. This
means each distinct endpoint gets its own concurrency semaphore in the
scheduler, preventing a slow endpoint from blocking all models.

In `RuntimePolicy.resolve()`, per-endpoint budgets are automatically created
for each unique `provider_id` found in the agent matrix. This is combined
with the AIMD controller so that budgets auto-adjust during the run.

---

## Where scheduling is still shallow

- Prepare is not a fully separate worker pool
- Provider headroom is visible but not used for dispatch prioritization
- `spec_hash` is computed but not used for batching or locality
- Finalize has no dedicated concurrency limit
- Phase-level retry is not implemented
