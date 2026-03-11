````md
# Runtime Scheduling v2

Current-state note:
Use `docs/architecture/runtime_and_scheduler.md` for the runtime behavior that exists in the repo today. This file is a forward-looking design document.

## Status

Draft for implementation.

## Purpose

This document defines the next-stage runtime scheduling model for Snowl.

The current runtime already has meaningful concurrency controls, including:

- `max_running_trials`
- `max_container_slots`
- `max_builds`
- `max_scoring_tasks`
- provider-level model concurrency budgets
- decoupled execute and score phases at a coarse level
- deferred retry queues

However, the current runtime is still best described as:

> multi-budget throttling plus a coarse trial pipeline, with important phases still partially synchronous and scheduler decisions still close to FIFO.

This document defines a concrete implementation direction for improving throughput, especially for container-heavy benchmarks, while keeping the user-facing Task / Agent / Scorer contracts stable.

---

## 1. Motivation

Snowl needs stronger runtime efficiency for real-world usefulness.

The main problem is not simply “increase concurrency.” The real problem is:

- scheduling trial work under heterogeneous resource constraints
- avoiding container and prepare churn
- overlapping prepare / execute / score more effectively
- preventing provider saturation from becoming opaque blocking
- improving throughput without turning the runtime into an unstable fanout engine

The current system already has important building blocks, but it still leaves substantial performance on the table because:

- container prepare/build/setup is still partly inside execute semantics
- docker-like workloads are still over-constrained by forced serial fallback
- the scheduler does not yet exploit `spec_hash` locality
- provider concurrency is enforced mainly at the client layer rather than as an explicit scheduler admission signal
- retry remains mostly whole-trial oriented

---

## 2. Current Runtime Limitations

### 2.1 Budgeting exists, but scheduling is still shallow

The runtime already uses multiple budgets rather than a single global concurrency number. This is the right foundation.

But the current scheduler is still primarily a queue + gating system rather than a resource-aware dispatcher. It can stop overload, but it does not yet make strong choices about which work should run next.

### 2.2 Execute and score are decoupled, but only coarsely

The runtime already prevents scoring from occupying the main running-trial slot. This is a meaningful improvement.

However, `PREPARE`, `EXECUTE`, and `SCORE` are not yet first-class independently scheduled phases. The scheduler still reasons mostly about whole-trial coroutines rather than phase-level work units.

### 2.3 Container-heavy paths still contain blocking behavior

Container prepare/build/setup is still partly synchronous and still occurs too close to execution. In practice this means some container-heavy workloads still behave like pseudo-concurrency rather than true pipelined concurrency.

### 2.4 Docker-like safety fallback is too conservative

The current forced default of `max_running_trials=1` for docker-like tasks avoids overload, but it also blocks legitimate throughput gains. It treats all container-backed workloads as if safe concurrency were unknowable.

### 2.5 No locality-aware dispatch

Trials are still dispatched roughly in plan order plus retry recovery rules. The runtime does not yet actively prefer trials that:

- share the same `spec_hash`
- can reuse the same warm setup
- can amortize prepare/build costs
- avoid provider saturation

### 2.6 Retry is still mostly whole-trial

Deferred retry already exists and is valuable, but it still treats failures too uniformly. A score failure is not the same as a prepare failure, and a prepare failure is not the same as an execute failure.

---

## 3. Goals and Non-Goals

## 3.1 Goals

This design aims to:

1. keep concurrency conceptually at the Task / Trial granularity
2. make scheduling phase-aware internally
3. make provider capacity a scheduler-visible admission signal
4. make container concurrency budget-driven rather than force-serialized by default
5. improve throughput for container-heavy benchmarks
6. exploit `spec_hash` locality for better reuse and less churn
7. add conservative canary-first behavior for new groups
8. improve observability so wait reasons and phase costs become explicit
9. keep user-facing authoring contracts stable

## 3.2 Non-Goals

This design does not aim to:

- rewrite the runtime from scratch
- introduce distributed scheduling
- introduce Rust or multiprocessing as part of this change
- redesign public `task.py`, `agent.py`, or `scorer.py` contracts
- build a mathematically optimal scheduler
- fully solve cross-run global caching in this phase

---

## 4. New Scheduling Model

The key design shift is:

> Snowl should continue to schedule at Task/Trial granularity, but trials should carry explicit resource plans and progress through independently governed phases.

This means:

- the scheduler does not dispatch arbitrary coroutines blindly
- the scheduler dispatches trial phases under explicit resource budgets
- each trial is represented by a scheduler-facing descriptor and plan

---

## 5. New Runtime Objects

### 5.1 TrialDescriptor

`TrialDescriptor` is a runtime-internal object representing the stable identity and scheduler state of a trial.

Suggested fields:

```python
@dataclass
class TrialDescriptor:
    trial_id: str
    task_id: str
    sample_id: str
    agent_id: str
    variant_id: str | None
    scorer_id: str | None
    seed: int | None

    spec_hash: str | None
    provider_ids: tuple[str, ...]
    phase: str
    retry_count: int = 0
````

Notes:

* this is not a new public user-facing API
* this exists for runtime scheduling, observability, and retry control
* `spec_hash` should be derived whenever a task/environment has a normalized sandbox or environment identity

### 5.2 TaskExecutionPlan

`TaskExecutionPlan` is a runtime-internal coarse resource estimate for a trial.

Suggested fields:

```python
@dataclass
class TaskExecutionPlan:
    trial: TrialDescriptor

    requires_container: bool
    requires_prepare: bool
    requires_build: bool

    estimated_agent_model_calls: int
    estimated_judge_model_calls: int
    estimated_total_model_calls: int

    estimated_steps: int
    estimated_duration_class: str   # light / medium / heavy
    estimated_prepare_cost: str     # none / light / heavy

    provider_ids: tuple[str, ...]
    spec_hash: str | None

    priority: float = 0.0
```

This estimate does not need to be perfect.

It only needs to be useful enough for:

* admission
* batching
* canary-first behavior
* coarse fairness
* observability

### 5.3 Resource Estimation Rules

The first implementation should use conservative heuristics.

Recommended defaults:

* `ChatAgent` -> `estimated_agent_model_calls = 1`
* `ReActAgent` -> estimate from configured `max_steps`, otherwise use a conservative fallback
* model-as-judge scorer -> `estimated_judge_model_calls = 1`
* rule-based / unit-test scorers -> `estimated_judge_model_calls = 0`

The runtime should also infer:

* whether a trial requires container-backed execution
* whether prepare/build is expected
* whether the workload is likely `light`, `medium`, or `heavy`

This estimate can later be refined with rolling in-run observations.

---

## 6. Trial Phases

Trials should move through explicit phases.

Recommended phases:

* `PENDING`
* `PREPARING`
* `READY`
* `EXECUTING`
* `SCORING`
* `FINALIZING`
* `SUCCEEDED`
* `FAILED`
* `BLOCKED`

This document focuses on the active runtime phases:

* `PREPARING`
* `READY`
* `EXECUTING`
* `SCORING`
* `FINALIZING`

### 6.1 PREPARING

This phase includes:

* image build / pull
* container or sandbox setup
* compose bring-up or preflight
* other environment preparation required before agent execution can start

`PREPARING` must be a real phase, not just hidden work inside execute.

### 6.2 READY

The trial has completed preparation and is eligible to enter execute when execution budgets allow.

This explicit phase is important because a trial may be prepared but still waiting for:

* running-trial capacity
* provider capacity
* scheduler priority

### 6.3 EXECUTING

This phase runs the agent and environment interaction.

### 6.4 SCORING

This phase runs scorer logic after execution completes.

Scoring must remain decoupled from execute slot ownership.

### 6.5 FINALIZING

This phase persists final results, emits final events, and releases or recycles resources.

---

## 7. Resource Budgets

The scheduler should continue to govern multiple budgets explicitly.

Required budgets:

* `max_running_trials`
* `max_container_slots`
* `max_builds`
* `max_scoring_tasks`
* provider budgets

### 7.1 PREPARING budget rules

`PREPARING` should be constrained by:

* `max_builds`
* `max_container_slots` when prepare requires container resources

`PREPARING` must not consume a running-trial slot.

### 7.2 EXECUTING budget rules

`EXECUTING` should be constrained by:

* `max_running_trials`
* provider budget admission
* container resource ownership where applicable

### 7.3 SCORING budget rules

`SCORING` should be constrained by:

* `max_scoring_tasks`
* provider budget admission if scorer uses a model

### 7.4 FINALIZING budget rules

`FINALIZING` should not be treated as a major throttled compute phase, but it must release resources and emit phase-complete observability data reliably.

---

## 8. Provider-Aware Admission

Provider concurrency must stop being only a client-side semaphore.

The client-side budget enforcement remains necessary as a final safety layer, but the scheduler should also know about provider dependency before dispatching work.

### 8.1 Required behavior

Each `TaskExecutionPlan` should carry the provider dependencies used by:

* agent execution
* scorer/judge execution

Before entering `EXECUTING`, the scheduler should consider provider availability.

Before entering `SCORING`, the scheduler should consider both:

* scoring slot availability
* provider availability when the scorer uses a model

### 8.2 Why this matters

Without scheduler-visible provider admission, a trial may be dispatched into a phase only to block deep inside the model client.

That makes the system:

* harder to explain
* harder to optimize
* less able to choose better alternative work

With scheduler-visible provider admission, the runtime can explicitly say:

* this trial is `READY` but waiting on provider capacity
* this score task is waiting on judge-provider capacity

That improves both throughput and observability.

---

## 9. Container-Capacity Defaulting

The current blanket fallback that forces docker-like workloads to serial execution is too conservative.

The new model should default to **budget-driven capacity** rather than **blanket serial fallback**.

### 9.1 Required change

Do not default docker-like workloads to `max_running_trials=1` unless there is a very specific hard reason.

Instead, derive a container-capacity estimate.

### 9.2 First implementation heuristic

A coarse heuristic is sufficient initially.

Suggested examples:

* terminalbench / compose-heavy terminal workloads -> default 2 container slots
* GUI-heavy OSWorld-like workloads -> default 1 or 2 container slots
* non-container benchmarks -> not applicable

User-provided overrides remain authoritative.

### 9.3 Effective execution concurrency

Effective task execution concurrency should be bounded by the intersection of:

* running-trial budget
* container capacity
* provider capacity

This is more accurate than a single docker-like serial switch.

---

## 10. Spec-Locality Scheduling

The scheduler should exploit `spec_hash` locality.

### 10.1 Motivation

Trials with the same `spec_hash` often share:

* image identity
* prepared environment shape
* container setup cost
* warm reuse opportunities

Running them near each other reduces:

* repeated prepare churn
* build/pull duplication
* warm pool misses

### 10.2 Required scheduling behavior

Pending work should be groupable by `spec_hash` where available.

The scheduler should prefer trials that:

* can hit a warm reusable environment
* match the active prepared group
* reduce expensive context switching between container specs

### 10.3 Initial heuristic

A simple heuristic is enough in this phase.

The priority score may combine:

* warm pool bonus
* spec batch bonus
* canary bonus
* waiting time bonus
* retry bonus
* prepare cost penalty
* provider saturation penalty

The runtime does not need an advanced optimizer yet.

---

## 11. Canary-First Dispatch

The runtime should validate new execution groups before broad fanout.

### 11.1 Grouping rule

For the first implementation, treat each `(spec_hash, agent_variant)` combination as a canary group.

### 11.2 Canary policy

For each unseen group:

* prioritize one canary trial first
* observe whether it succeeds
* if it fails due to systemic prepare/setup/runtime reasons, block or pause the group

### 11.3 Benefits

This prevents:

* mass fanout of broken specs
* repeated expensive setup failure
* late discovery of systemic runtime issues

### 11.4 Conservative implementation

The policy should remain simple in the first pass:

* first trial per group is the canary
* failed canary may block remaining group work
* group block reason must be surfaced in events and summary artifacts

---

## 12. Phase-Aware Retry

Retry must become phase-aware, even if only minimally in the first implementation.

### 12.1 Distinguish failure classes

At minimum distinguish:

* prepare failure
* execute failure
* score failure

### 12.2 Required behavior

* score failure should be retryable without rerunning execute when possible
* prepare failure should retry the prepare phase rather than always restarting the whole trial
* execute failure may still retry at trial scope where necessary

### 12.3 Compatibility rule

When phase-specific retry is not feasible, preserve existing whole-trial retry behavior.

The goal is incremental improvement, not a full recovery engine rewrite.

---

## 13. Observability and Metrics

This change must improve runtime explainability.

The scheduler should emit explicit timing and wait signals for each major phase.

### 13.1 Required per-trial metrics/events

At minimum add:

* prepare queue wait
* prepare wall time
* execute queue wait
* execute wall time
* score queue wait
* score wall time
* provider wait or provider admission delay
* container slot wait
* build slot wait
* canary success/failure
* group blocked reason
* `spec_hash`
* `provider_ids`
* phase transition timestamps

### 13.2 Artifact requirements

* `run.log` should remain readable for humans
* `events.jsonl` should stay structured for machine analysis
* wait reasons should become explicit rather than inferred indirectly
* existing artifact consumers should not be broken unnecessarily

### 13.3 Why this matters

Without explicit phase-level observability, throughput work becomes guesswork.

The runtime must be able to answer:

* what is waiting
* why it is waiting
* which resource budget is constraining progress
* whether time is being spent in prepare, execute, or score

---

## 14. Scheduling Semantics Summary

The scheduling model should now behave as follows.

### 14.1 Planning / materialization

When trials are materialized, construct:

* `TrialDescriptor`
* `TaskExecutionPlan`

### 14.2 PREPARING dispatch

A trial enters `PREPARING` when:

* it requires environment setup
* build/container budgets allow
* scheduler priority admits it

### 14.3 READY state

After prepare completes, the trial becomes `READY`.

A `READY` trial may wait for:

* running-trial capacity
* provider capacity
* scheduler prioritization

### 14.4 EXECUTING dispatch

A `READY` trial enters `EXECUTING` when:

* running-trial budget allows
* relevant provider budget allows
* dispatch priority selects it

### 14.5 SCORING dispatch

After execution completes:

* the trial transitions to `SCORING`
* execution slot is released
* scoring proceeds under scoring budget and provider admission

### 14.6 FINALIZING

After scoring completes or terminal failure is reached:

* trial transitions to `FINALIZING`
* final artifacts and diagnostics are persisted
* resources are released or recycled explicitly

---

## 15. Compatibility

This design should preserve the existing user contract:

* `task.py`
* `agent.py`
* `scorer.py`
* benchmark adapters

The main changes are runtime-internal.

Compatibility goals:

* no required user-facing API changes
* no new mandatory YAML or config surface
* existing model-client provider controls remain intact
* existing artifact files remain present where practical
* behavior changes should mostly improve concurrency and observability rather than alter evaluation semantics

---

## 16. Implementation Plan

### Phase 1

Introduce scheduler-facing runtime objects:

* `TrialDescriptor`
* `TaskExecutionPlan`

Build them during trial planning/materialization.

### Phase 2

Split container prepare/build/setup into a true `PREPARING` phase.

* move blocking setup out of execute
* wrap blocking operations using `asyncio.to_thread(...)` or equivalent async boundary
* ensure `PREPARING` is governed by build/container budgets
* ensure `PREPARING` does not consume a running-trial slot

### Phase 3

Replace docker-like forced serial fallback with budget-driven default container capacity.

### Phase 4

Promote provider dependency into scheduler admission.

* scheduler should know provider requirements before dispatching execute/score
* client-level provider slots remain as safety

### Phase 5

Add `spec_hash` locality-aware scheduling.

### Phase 6

Add canary-first dispatch.

### Phase 7

Add phase-level metrics and explicit wait reasons.

### Phase 8

Add minimal phase-aware retry support.

---

## 17. Testing Plan

Add or update tests to verify:

1. `PREPARING` does not consume running-trial slots
2. scoring remains decoupled from execute slots
3. provider-saturated trials remain `READY` rather than entering opaque client-only blocking
4. docker-like workloads no longer force serial execution by default when safe heuristic capacity allows more than one slot
5. locality heuristics prefer warm/spec-matching trials
6. failed canary blocks or pauses remaining group work
7. score-only retry can occur without rerunning execute when supported
8. events and artifacts include phase timing and wait-reason information

An additional benchmark-style integration test should verify:

* multiple container tasks can prepare/execute under container slot limits greater than one
* multiple trials sharing a provider can issue concurrent model calls up to budget
* scoring continues while new execution tasks start

---

## 18. Deferred Work

The following are explicitly deferred beyond this implementation:

* advanced fairness models
* distributed or multi-host scheduling
* cross-run learned cost prediction
* global retry storm control beyond simple safeguards
* full provider token-budget arbitration
* mathematically complex scheduling optimization

These may become future follow-ups once the phase-aware scheduler foundation is in place.

---

## 19. Conclusion

Runtime efficiency in Snowl is not just a matter of “more concurrency.”

The important shift is to schedule Task-level trials using explicit resource plans and independently governed phases.

The first meaningful step is not a rewrite. It is a targeted upgrade:

* make `PREPARING` real
* make provider capacity scheduler-visible
* replace blanket docker-like serialization with budget-driven defaults
* exploit `spec_hash` locality
* add canary-first behavior
* improve phase-level observability

This keeps the system understandable while unlocking the next real throughput gains, especially for container-heavy evaluation workloads.
