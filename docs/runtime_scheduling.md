# Runtime Scheduling and Concurrency Design for Snowl

Current-state note:
Use `docs/architecture/runtime_and_scheduler.md` for the runtime behavior that exists in the repo today. This file is a forward-looking design/planning document.

## Status

Draft for implementation planning.

## Purpose

This document defines the runtime scheduling model for Snowl as the framework moves from a functional evaluation runner toward a reliable, high-throughput, production-usable execution system.

The main goal is not merely to “run more trials in parallel,” but to schedule heterogeneous evaluation work under real resource constraints:

* sandbox/container lifecycle cost
* model API rate limits
* scoring overhead
* failure recovery needs
* reproducibility requirements
* interactive user experience expectations

Snowl should therefore treat runtime scheduling as a first-class systems problem.

---

## 1. Design Goal

Snowl runtime should evolve from a simple concurrent executor into a **resource-aware, phase-aware, and failure-aware trial scheduler**.

This means:

* the scheduler must understand that different phases of a trial consume different resources
* the runtime must optimize for sandbox reuse and preparation deduplication
* scoring must not unnecessarily block execution capacity
* concurrency must be bounded by explicit resource budgets rather than a single global worker count
* retry and resume behavior must preserve expensive successful work whenever possible

In practical terms, Snowl should behave more like a lightweight evaluation operating system than a naive async task runner.

---

## 2. Core Observation

The unit being scheduled is not simply a Python function or even a whole trial as one opaque task.

A `Task x AgentVariant x Sample` trial is a multi-phase pipeline with different cost centers.

A good scheduler must decide not only:

* how many trials run at once

but also:

* which phase each trial may enter now
* which resource budget is being consumed
* whether a trial should wait for warm reuse
* whether scoring should be deferred
* whether a failing group should be paused before bulk fanout

---

## 3. Trial as a Multi-Phase Pipeline

Snowl should model each trial as a stateful execution pipeline rather than one indivisible job.

Recommended phases:

1. **Resolve / Plan**

   * expand benchmark/provider/sample/agent/scorer inputs
   * compute stable trial identity
   * compute `spec_hash`
   * derive resource requirements

2. **Prepare**

   * build image
   * pull image
   * sync assets
   * provision sandbox template
   * perform spec-specific initialization

3. **Acquire Runtime Slot**

   * lease a warm sandbox from pool, or create a new runtime instance

4. **Execute Agent**

   * run model loop
   * perform tool calls
   * interact with environment
   * emit trace and usage events

5. **Score**

   * apply deterministic rule scorers, unit-test scorers, or model-as-judge scorers

6. **Finalize / Persist**

   * write results
   * flush artifacts
   * store diagnostics
   * release or recycle sandbox resources

This phase separation is the foundation for better scheduling.

---

## 4. Trial State Machine

Snowl should promote the trial lifecycle to an explicit runtime state machine.

Recommended states:

* `PENDING`
* `PREPARING`
* `READY`
* `RUNNING`
* `SCORING`
* `FINALIZING`
* `SUCCEEDED`
* `FAILED`
* `CANCELLED`
* `BLOCKED`

### Why this matters

Without a clear state machine, concurrency control becomes blurry and failure recovery becomes expensive.

With explicit phase states, Snowl can:

* apply different concurrency limits to different phases
* retry only the failing phase when possible
* surface better observability in CLI/Web UI
* checkpoint progress more accurately
* support blocked groups and partial pause/resume behavior

---

## 5. TrialDescriptor as a First-Class Scheduling Object

To support runtime scheduling cleanly, Snowl should introduce a scheduler-facing execution object.

Suggested structure:

```python
class TrialDescriptor:
    trial_id: str
    run_id: str
    task_id: str
    sample_id: str
    agent_id: str
    variant_id: str | None
    scorer_id: str
    seed: int | None

    spec_hash: str
    phase: str
    priority: float
    estimated_cost: dict[str, float]
    retry_state: dict[str, object]
    requirements: dict[str, object]
```

### Role of TrialDescriptor

This object is not user-facing. It exists so the runtime can:

* sort work
* batch by `spec_hash`
* assign retries
* checkpoint scheduler state
* estimate cost and latency
* resume safely

`Task`, `Agent`, and `Scorer` remain the product-facing abstractions. `TrialDescriptor` becomes the runtime-facing abstraction.

---

## 6. Resource-Aware Concurrency Model

Snowl should stop thinking of concurrency as one number.

A single `max_concurrency` flag is too crude for agent evaluation workloads because different phases stress different subsystems.

The runtime should instead use separate resource budgets.

### 6.1 Build Budget

Controls concurrent expensive preparation work.

Examples:

* image build
* image pull
* dependency sync
* heavy asset setup

Suggested control:

* `max_builds`

### 6.2 Sandbox Budget

Controls the number of active warm or leased sandbox instances.

Suggested control:

* `max_sandboxes`

### 6.3 Execution Budget

Controls the number of trials actively running agent logic.

Suggested control:

* `max_running_trials`

This should be separate from sandbox count because not every sandbox is always actively executing.

### 6.4 Model Call Budget

Controls API pressure against model providers.

This is important because both agents and scorers may call models.

Suggested controls:

* `max_model_calls_global`
* `max_model_calls_per_provider`
* `max_model_calls_per_model`

Longer term, Snowl may also track token budgets or requests-per-minute budgets.

### 6.5 Scoring Budget

Controls scoring concurrency independently from execution concurrency.

Suggested control:

* `max_scoring_tasks`

This allows score-heavy runs to avoid blocking main trial throughput.

### 6.6 Artifact / Writer Budget

Usually lower priority, but high-volume tracing can create IO pressure.

Suggested approach:

* one buffered writer pipeline
* bounded queues
* batch flush intervals

---

## 7. Scheduling Principle: Optimize for Spec Locality

The most important scheduling optimization in Snowl is not generic FIFO concurrency. It is **spec locality**.

If two trials share the same `spec_hash`, they are likely to share:

* image build artifacts
* pulled images
* prepared assets
* reusable warm sandboxes

Therefore, Snowl should prefer running same-spec trials near each other in time.

### Why spec locality matters

Naive ordering such as:

* `A -> B -> A -> B -> A -> B`

causes repeated setup churn and poor warm-pool utilization.

A grouped ordering such as:

* `A -> A -> A -> B -> B -> B`

gives much better reuse and lower startup cost.

### Recommended structure

The scheduler should maintain per-spec queues:

```text
spec_hash_A -> [trial1, trial2, trial3]
spec_hash_B -> [trial4, trial5]
spec_hash_C -> [trial6, trial7, trial8]
```

Within a spec group, the runtime may further sort by agent/model or estimated cost.

---

## 8. Scheduler Goals: Throughput vs. First Result Latency

Snowl should explicitly support two different scheduling goals.

### 8.1 Throughput-Oriented Scheduling

Best for large benchmark runs.

Goals:

* maximize warm sandbox reuse
* minimize build churn
* keep execution resources saturated
* reduce total makespan

Behavior:

* stronger spec batching
* stronger prepare deduplication
* willingness to delay isolated trials if batching improves total throughput

### 8.2 Interactive / First-Result Scheduling

Best for local development and debugging.

Goals:

* produce first useful results quickly
* surface setup or scoring errors early
* cover multiple groups before committing full fanout

Behavior:

* run canaries first
* sample more groups early
* prioritize debuggability over optimal total throughput

### 8.3 Suggested Scheduler Profiles

Snowl should expose high-level scheduler profiles instead of too many low-level flags.

Suggested profiles:

* `interactive`
* `throughput`
* `deterministic`

This keeps the CLI surface smaller while still allowing meaningful control.

---

## 9. Canary Before Bulk Fanout

A major source of wasted time in evaluation systems is bulk launching trials before validating that the setup actually works.

Examples of expensive late-discovered errors:

* broken sandbox spec
* incompatible tool/env requirements
* invalid scorer template placeholders
* agent contract failures
* benchmark row mapping bugs

Snowl should therefore introduce a **canary phase**.

### Recommended behavior

Before full fanout, run a small number of representative samples per scheduling group, such as:

* one or two trials per `(spec_hash, agent_variant)`
* or one or two trials per `(task family, spec_hash, agent_variant)`

### Benefits

* catches configuration issues early
* prevents mass failure storms
* gives users fast signal in interactive runs
* enables early latency and cost estimation

### Failure handling

If canary failure rate is too high, the runtime should:

* pause or block the affected group
* mark it as `BLOCKED`
* surface the reason clearly in CLI/Web UI
* avoid launching the rest of that group automatically

---

## 10. Warm Pool Design: Reuse Requires Health and Lease Management

A warm pool should not be treated as a simple cache.

Reusable runtime instances need explicit lifecycle management.

### Recommended sandbox state model

Each sandbox should track:

* `sandbox_id`
* `spec_hash`
* `state`: `idle | leased | dirty | recycling | dead`
* `created_at`
* `last_used_at`
* `lease_owner_trial_id`
* `reuse_count`
* `health_score`
* `startup_latency_ms`
* `last_failure_reason`

### Why this matters

Many evaluation environments are not safely reusable without reset.

Common problems:

* leftover files
* background processes
* consumed ports
* broken GUI/session state
* partial asset mutation

### Return-to-pool logic

After a trial finishes:

* if reset succeeds and health is acceptable, return sandbox to `idle`
* otherwise move it to `recycling` or destroy it

A pool that ignores environment dirtiness will slowly drift into flaky and irreproducible behavior.

### Lease timeout

The pool should also support:

* heartbeat or progress updates
* lease timeout
* forced reclaim or teardown for stalled trials

---

## 11. Preparation Must Use Single-Flight Deduplication

Hash-based reuse is not enough by itself.

If multiple workers discover the same missing `spec_hash` at the same time, they may still trigger duplicated preparation work.

Snowl should enforce **single-flight prepare** semantics per `spec_hash`.

### Single-flight rule

At any point in time, only one prepare operation may be in flight for the same `spec_hash`.

Behavior:

* the first requester performs the build/pull/setup
* all other trials needing the same spec wait on that single in-flight preparation
* if prepare succeeds, all waiting trials reuse the result
* if prepare fails, failure is propagated consistently and retry policy is applied once

### Benefits

* avoids duplicate image builds
* reduces wasted CPU, disk, and network traffic
* simplifies failure propagation
* aligns naturally with per-spec scheduling queues

---

## 12. Scoring Must Be Decoupled from Execution

Scoring should not hold onto execution slots longer than necessary.

This is especially important when:

* model-as-judge is used
* unit tests are slow
* multiple metrics are computed post-run

### Problem with coupled scoring

If a worker runs:

1. agent execution
2. scoring
3. finalization

then expensive scoring delays release of sandbox and execution capacity.

### Recommended model

Snowl should separate:

* **run pool**: executes agent logic
* **score pool**: executes scorer logic

### Runtime consequence

Once agent execution completes:

* sandbox can be released or recycled earlier
* the trial enters `SCORING`
* scoring continues asynchronously

This increases effective sandbox throughput and keeps container-heavy workloads moving.

---

## 13. Bounded Queues and Backpressure

Large-scale eval planning can easily produce more work than memory, IO, or UI layers should absorb at once.

Snowl should introduce bounded pipelines.

### 13.1 Bounded Planning Window

The planner should lazily expand trials rather than materialize everything immediately.

Suggested approach:

* maintain a bounded pending buffer
* continue pulling from `TaskProvider` only when scheduler capacity frees up

This is especially important for large benchmark datasets.

### 13.2 Bounded Event Pipeline

Tracing and observability can become a hidden bottleneck.

Suggested approach:

* one structured event writer pipeline
* queue size limits
* batch flushes
* optional degradation under severe pressure

### 13.3 UI Aggregation

Live UI should not render every low-level event naively.

Suggested approach:

* aggregate or sample high-frequency events
* collapse repetitive command output
* preserve full logs in artifacts even when UI shows summarized views

Without backpressure, the runtime may destabilize itself by overproducing internal data.

---

## 14. Cost Model and Rolling Statistics

Even a simple scheduler benefits from a basic cost model.

Snowl should maintain rolling stats to inform scheduling choices.

### Suggested per-spec statistics

* prepare latency p50/p95
* startup latency p50/p95
* run latency p50/p95
* failure rate
* reset success rate
* reuse efficiency

### Suggested per-agent/model statistics

* average step count
* average model latency
* average prompt/completion tokens
* tool-call frequency
* score latency

### Uses of this data

* rough ETA estimation
* scheduling priority decisions
* anomaly detection
* fairness adjustment
* UI summaries
* future adaptive scheduling

The first implementation can be rough. It does not need a sophisticated predictor.

---

## 15. Fairness vs. Efficiency

Pure efficiency optimization can starve less common spec groups.

For example, if the scheduler always prefers the largest warm-ready group, small or expensive groups may wait indefinitely.

Snowl should therefore support **efficiency-biased fairness**.

### Recommended principle

Prefer same-spec locality and warm hits, but apply aging to waiting groups.

Possible mechanisms:

* waiting-time bonus
* starvation threshold
* max consecutive dispatches from one group before reassessment

This allows Snowl to remain efficient without becoming unfair.

---

## 16. Deterministic Identity vs. Deterministic Execution Order

Reproducibility is essential, but concurrency complicates what reproducibility means.

Snowl should distinguish between two levels.

### 16.1 Deterministic Trial Identity (Required)

This must remain stable:

* dataset fingerprint
* task/agent/scorer version IDs
* sample ID
* variant ID
* seed
* env image digest or `spec_hash`
* exact model version

### 16.2 Deterministic Execution Order (Optional)

Under concurrency, execution order often depends on runtime conditions.

Snowl should make deterministic ordering a configurable profile rather than a universal guarantee.

Suggested profile:

* `deterministic`

This may sacrifice throughput in exchange for repeatable ordering and simpler debugging.

---

## 17. Phase-Specific Retry and Recovery

Retry should not be modeled as “rerun the whole trial” in every case.

Different failure phases deserve different recovery logic.

### 17.1 Prepare Failure

Examples:

* image pull failure
* build failure
* asset sync error

Recommended handling:

* retry at `spec_hash` level
* use backoff
* block the whole group after threshold failure

### 17.2 Run Failure

Examples:

* agent exception
* model timeout
* tool execution error
* env crash

Recommended handling:

* retry at trial level
* possibly acquire a fresh sandbox
* preserve diagnostics from failed attempt

### 17.3 Score Failure

Examples:

* judge model timeout
* malformed judge output
* template rendering error

Recommended handling:

* rerun scoring only
* do not rerun agent execution unless required

This phase-specific recovery model saves both time and money.

---

## 18. Scheduler Architecture Recommendation

Snowl runtime should adopt a small number of explicit components rather than a loose collection of async functions.

Suggested components:

### 18.1 Planner

* lazily expands task/agent/sample combinations
* emits `TrialDescriptor`s

### 18.2 Scheduler

* decides which trial enters which phase next
* enforces policy, priorities, and fairness

### 18.3 Prepare Manager

* handles single-flight prepare
* manages build queue
* records prepare outcomes by `spec_hash`

### 18.4 Sandbox Pool Manager

* owns warm pool lifecycle
* handles lease, reset, recycle, and health checks

### 18.5 Execution Workers

* run agents
* stream trace and usage events

### 18.6 Scoring Workers

* run scorers independently from execution workers

### 18.7 Artifact Writer

* buffers and persists events, trial rows, diagnostics, and summaries

### 18.8 Run State Store

* stores checkpoint and resumability metadata
* persists scheduler-visible state transitions where needed

### Event model

These components should communicate through explicit runtime events such as:

* `TrialQueued`
* `PrepareStarted`
* `PrepareFinished`
* `SandboxLeased`
* `TrialRunning`
* `TrialFinished`
* `ScoreStarted`
* `ScoreFinished`
* `TrialFinalized`
* `GroupBlocked`

This event-driven structure makes observability and debugging much cleaner.

---

## 19. Recommended Scheduler Heuristic (MVP)

Snowl does not need a perfect scheduler for its first implementation. It needs one that captures the highest-value system behaviors.

Recommended MVP policy:

1. **Run canaries first**

   * small validation subset per spec group or `(spec_hash, agent_variant)` group

2. **Use single-flight preparation**

   * deduplicate all concurrent prepare work by `spec_hash`

3. **Prefer warm-ready groups**

   * groups with already prepared idle sandboxes get priority

4. **Batch same-spec trials in short bursts**

   * keep locality high without starving other groups

5. **Separate run and score pools**

   * release sandbox resources as soon as execution finishes

6. **Block failing groups**

   * if canary or repeated prepare failure crosses threshold, pause the group

7. **Use bounded planning**

   * do not expand the whole dataset at once

### Why this MVP is strong

This design already addresses the main real-world pain points:

* duplicate builds
* poor sandbox reuse
* late-discovered configuration failures
* scoring blocking main execution
* unstable high-volume runs

---

## 20. Example Priority Function

The scheduler does not need a perfect mathematical optimizer. A practical weighted heuristic is enough.

A conceptual priority score could combine:

* warm pool bonus
* same-spec batching bonus
* retry bonus
* small-remaining-group bonus
* waiting-time bonus
* estimated prepare cost penalty

Conceptually:

```text
priority =
  warm_pool_bonus
  + spec_batch_bonus
  + retry_bonus
  + waiting_time_bonus
  - estimated_prepare_cost
```

The exact weights can evolve later. The important point is that the scheduler should prefer work that is cheap to start and valuable to complete, without permanently starving other groups.

---

## 21. Scheduler Profiles

Snowl should expose high-level scheduler presets rather than a large number of user-facing flags.

### `interactive`

Use when the user wants fast validation and debugging.

Characteristics:

* stronger canary behavior
* broader early coverage
* weaker batching preference
* prioritize first result latency

### `throughput`

Use for large benchmark sweeps.

Characteristics:

* stronger spec locality
* aggressive warm reuse
* stronger prepare deduplication
* prioritize total makespan

### `deterministic`

Use for reproducibility-sensitive reruns and debugging.

Characteristics:

* stable ordering rules
* limited opportunistic reshuffling
* lower throughput acceptable

---

## 22. Observability Requirements for Scheduler Quality

Scheduling decisions must be visible. Otherwise performance and fairness issues become impossible to reason about.

Snowl should record at least:

* `spec_hash`
* prepare/build identifiers
* sandbox IDs and lease transitions
* startup latency
* reset/recycle results
* queue wait times by phase
* scoring wait times
* retry counters by phase
* group block reasons

This data should be available both in artifacts and in live UI summaries.

### Useful derived metrics

* warm pool hit rate
* duplicated prepare avoided
* average queue wait per phase
* score lag vs. run lag
* failure concentration by spec group
* sandbox reuse count distribution

---

## 23. Proposed Runtime Scheduling Principles

Snowl runtime scheduling should follow these principles.

1. **Phase-aware scheduling**

   * `prepare`, `run`, `score`, and `finalize` are governed independently

2. **Resource-aware concurrency**

   * different resources must have separate budgets

3. **Spec-locality optimization**

   * prefer same-`spec_hash` batching to maximize reuse

4. **Single-flight preparation**

   * identical spec preparation must deduplicate in-flight work

5. **Canary before bulk fanout**

   * validate groups before large-scale launch

6. **Decoupled scoring**

   * scoring should not hold execution slots unnecessarily

7. **Bounded planning and backpressure**

   * lazy expansion and bounded queues are required for stability

8. **Deterministic identity, optional deterministic order**

   * reproducible results are mandatory; reproducible scheduling order is configurable

9. **Phase-specific retry/recovery**

   * do not repeat expensive successful phases when later phases fail

10. **Observable scheduling decisions**

* runtime must explain where time and resources go

---

## 24. MVP Implementation Order

Recommended implementation order:

### P0

* trial phase state machine
* `TrialDescriptor`
* single-flight prepare by `spec_hash`
* warm pool lease/health model
* run/scoring decoupling
* canary phase
* bounded queues and writer backpressure

### P1

* spec-aware priority scheduling
* rolling cost statistics
* scheduler profiles (`interactive`, `throughput`, `deterministic`)
* blocked-group pause/resume semantics

### P2

* adaptive scheduling from historical latency/cost data
* token-budget-aware provider scheduling
* cross-run prepare cache optimization
* multi-host or distributed execution

---

## 25. Non-Goals for Initial Implementation

The first scheduling implementation should not attempt to solve everything.

Not required in the first pass:

* multi-machine distributed scheduling
* full predictive autoscaling
* perfect global optimality
* provider-specific token arbitration beyond coarse budgets
* deeply benchmark-custom scheduling policies

The initial objective is a system that is clearly better than naive concurrency while remaining understandable and debuggable.

---

## 26. Conclusion

Snowl should not frame runtime efficiency as a generic parallelism problem.

The real problem is scheduling multi-phase trials under heterogeneous resource constraints while preserving reuse, reliability, and reproducibility.

The central design shift is this:

> Snowl runtime should become a scheduler for `trial + sandbox + model budget`, not just a concurrent runner for Python tasks.

That shift unlocks the next stage of product quality:

* faster large-scale evaluations
* more stable container-backed runs
* earlier failure detection
* better user-facing interactivity
* lower wasted compute and API spend
* stronger operational clarity

This should be treated as a core runtime direction for Snowl, not a secondary optimization.
