# 03: Concurrency Architecture

## 3.1 Current Model Analysis

### Semaphore Hierarchy

```
ResourceScheduler
  ├── max_running_trials (asyncio.Semaphore)
  │     Controls: concurrent agent.run() calls
  │     Acquired: begin_execute()
  │     Default: min(8, cpu_count)
  │
  ├── max_container_slots (asyncio.Semaphore)
  │     Controls: concurrent sandbox/container operations
  │     Acquired: begin_prepare(), acquire_sandbox_slot()
  │     Default: auto (0 for local, 2-4 for Docker)
  │
  ├── max_scoring_tasks (asyncio.Semaphore)
  │     Controls: concurrent scorer.score() calls
  │     Acquired: begin_score()
  │     Default: = max_running_trials
  │
  ├── max_builds (threading.BoundedSemaphore)
  │     Controls: concurrent Docker image builds
  │     Acquired: build_slot()
  │     Default: 2
  │
  └── provider_budgets[id] (asyncio.Semaphore per provider)
        Controls: concurrent model API calls per provider
        Acquired: provider_admission()
        Default: max(running_trials, scoring_tasks)
        Wire: OpenAICompatibleChatClient -> global slot resolver
```

### Dispatch Loop

```python
# In snowl/eval.py (simplified)
max_inflight = max_running_trials + max_scoring_tasks
inflight: set[asyncio.Task] = set()

while trials_remaining or inflight:
    # Dispatch new trials up to max_inflight
    while len(inflight) < max_inflight and trials_remaining:
        trial = next_trial()
        task = asyncio.create_task(lifecycle.run(trial_index, trial))
        inflight.add(task)

    # Wait for any completion
    done, inflight = await asyncio.wait(inflight, return_when=FIRST_COMPLETED)

    # Process completed trials
    for task in done:
        outcome = task.result()
        process_outcome(outcome)
```

### Concurrency Flow Per Trial

```
                prepare  execute   score   finalize
                ───────  ───────   ─────   ────────
container_slot:  [██]                          [██]
running_trial:            [████████████]
scoring_task:                       [████]
provider_budget:    [██]  [██████]  [██]
                         ^         ^
                         |         |
                    agent.run()  scorer.score()
                    (per model   (asyncio.to_thread,
                     call)        no provider admission)
```

## 3.2 Problems for ToolEmu & AgentDojo

### P1: API Call Amplification is Unaccounted For

A single ToolEmu trial with LM-emulated sandbox makes:
- 1 agent LM call per thought step
- 1 emulator LM call per tool invocation
- 1 critiquer LM call per emulator output
- ~10 steps x 2 tool calls per step = ~30 LM calls per trial

With 8 concurrent trials, that's 240 concurrent API demands, far exceeding typical rate limits (60-120 RPM for GPT-4).

The `provider_budget` semaphore is acquired per `generate()` call, so individual calls are throttled, but:
- Trials block on provider admission while holding `running_trial` slots
- No backpressure from provider to dispatcher

**Impact**: API rate limit errors, wasted trial slots, high retry rate.

### P2: Scorer Cannot Use Provider Admission

```python
# Current: score_trial_phase
scores = await asyncio.to_thread(request.scorer.score, task_result, trace, score_context)
```

The scorer runs in a thread pool, completely outside the async event loop. It cannot:
- Acquire provider admission for judge model calls
- Participate in the scheduler's provider budget
- Be throttled by rate limits

**Impact**: If a scorer makes LM calls (ToolEmu's LM evaluator), they bypass rate limiting.

### P3: No Within-Trial Parallelism

ToolEmu's `FuncExecutorWithRetry` processes batches of 5-10 cases in parallel using `ThreadPoolExecutor`. In Snowl, each case is a separate trial, and concurrency is only between trials.

For AgentDojo, running clean + attacked variants of the same user task requires two separate trials with no coordination.

**Impact**: Suboptimal throughput for benchmarks that benefit from batch-level parallelism.

### P4: Docker-like Heuristic is Binary

```python
def is_docker_like_task(task):
    # Returns True for terminal/gui/docker env types OR terminalbench/osworld
    # Forces max_running_trials=1
```

This is too coarse. Many container-based benchmarks could run 2-4 concurrent containers on modern hardware. The heuristic should be per-benchmark tunable.

**Impact**: Unnecessarily serial execution for container-based benchmarks.

## 3.3 Proposed Concurrency Model

### Layer 1: Async Scorer Protocol

```python
class AsyncScorer(Protocol):
    scorer_id: str
    async def ascore(self, task_result, trace, context) -> dict[str, Score]

# Backward compatibility: sync scorers wrapped automatically
class SyncScorerAdapter:
    def __init__(self, inner: Scorer): ...
    async def ascore(self, task_result, trace, context):
        return await asyncio.to_thread(inner.score, task_result, trace, context)
```

The `score_trial_phase` would call `ascore()` directly, and the async scorer can acquire provider admission:

```python
async def score_trial_phase(prepared, partial):
    if hasattr(scorer, 'ascore'):
        scores = await scorer.ascore(task_result, trace, score_context)
    else:
        scores = await asyncio.to_thread(scorer.score, task_result, trace, score_context)
```

### Layer 2: Benchmark Concurrency Profiles

```python
@dataclass(frozen=True)
class BenchmarkConcurrencyProfile:
    """Benchmark-specific guidance for RuntimePolicy."""
    name: str

    # Per-trial API call amplification factor
    # ToolEmu with emulation: ~30 calls/trial
    # AgentDojo: ~5 calls/trial
    # Simple QA: ~1 call/trial
    api_call_amplification: float = 1.0

    # Recommended max_running_trials (overrides heuristic)
    recommended_max_running: int | None = None

    # Whether trials within this benchmark can share state
    supports_trial_isolation: bool = True

    # Whether scoring requires provider admission
    scorer_uses_provider: bool = False

    # Provider to use for scorer (if scorer_uses_provider)
    scorer_provider_id: str | None = None
```

Registered alongside `BenchmarkInfo`:

```python
BenchmarkInfo(
    name="toolemu",
    concurrency_profile=BenchmarkConcurrencyProfile(
        api_call_amplification=30.0,
        recommended_max_running=3,  # 3 trials x 30 calls = 90 concurrent
        scorer_uses_provider=True,
        scorer_provider_id="openai",
    ),
)
```

### Layer 3: Provider-Aware Dispatch

Currently, the dispatch loop doesn't consider provider availability when choosing which trial to dispatch next. This leads to:

- Trials entering prepare phase when provider is saturated
- All trials competing for the same provider budget

**Proposed**: Provider headroom as a dispatch gate:

```python
while len(inflight) < max_inflight and trials_remaining:
    trial = next_trial()

    # Check provider headroom before dispatching
    provider_id = trial_provider_id(trial)
    amplification = get_amplification(trial)
    if not scheduler.provider_headroom(provider_id, amplification):
        continue  # Skip this trial, try another or wait

    task = asyncio.create_task(lifecycle.run(trial_index, trial))
    inflight.add(task)
```

### Layer 4: Emulated Tool Execution with Provider Admission

For ToolEmu's LM-emulated sandbox:

```python
class EmulatedToolWrapper:
    """Wraps tool callables with LM-emulated execution."""

    def __init__(self, emulator_llm, critiquer_llm=None, simulator_type="std_thought"):
        self.emulator = emulator_llm
        self.critiquer = critiquer_llm
        self.simulator_type = simulator_type

    async def execute(self, tool_name, tool_args, scratchpad, scheduler):
        async with scheduler.provider_admission(self.emulator.provider_id):
            observation = await self.emulator.generate(
                prompt=self._build_emulation_prompt(tool_name, tool_args, scratchpad)
            )
        if self.critiquer:
            async with scheduler.provider_admission(self.critiquer.provider_id):
                observation = await self.critiquer.revise(observation)
        return observation
```

This requires the `Agent.run()` method to pass through the scheduler to tool execution. Currently, tools are sync callables. We need:

1. An `AsyncToolSpec` with `async def execute(**kwargs) -> Any`
2. The `ReActAgent` to call `await tool.execute()` instead of `tool.callable()`
3. Provider admission integrated into the tool execution path

### Layer 5: Sample-Level Parallelism (Future)

For benchmarks that benefit from running multiple samples of the same task concurrently:

```python
@dataclass
class SampleParallelConfig:
    max_concurrent_samples: int = 1
    sample_batch_size: int | None = None  # None = all at once
```

This would allow a single task with 144 samples to process 10 at a time within one "trial", rather than creating 144 separate trials. However, this requires significant refactoring of the trial lifecycle and is proposed as a Phase 3 item.

## 3.4 Concurrency Model Comparison

### Current vs Proposed for ToolEmu (144 cases, emulation mode)

| Aspect | Current | Proposed |
|--------|---------|----------|
| Running trials | 8 (default) | 3 (profiled) |
| API calls per trial | ~1 (stub tools) | ~30 (emulated) |
| Concurrent API demand | ~8 | ~90 (provider_budget=30 controls this) |
| Scorer | sync, no provider | async, with provider admission |
| Scorer API calls | 0 | ~2 per sample (evaluator + critiquer) |
| Total API calls | ~144 | ~4,608 (144 x 30 agent + 144 x 2 scorer) |
| Estimated throughput | ~144/5min | ~144/30min (with emulation) |
| Provider saturation | Low | High, but controlled |

### Current vs Proposed for AgentDojo (97 tasks, clean+attacked)

| Aspect | Current | Proposed |
|--------|----------|----------|
| Running trials | 8 | 8 |
| Runs per task | 1 (combined) | 2 (clean + attacked) |
| Total trials | 97 | 194 |
| Stateful tools | No (stubs) | Yes (real state mutations) |
| Injection middleware | N/A | Yes (modifies tool outputs) |
| Scorer | sync, state checks only | async, stateful + policy |
