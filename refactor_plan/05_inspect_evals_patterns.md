# 05: inspect_evals Reference Patterns

## 5.1 Patterns Worth Borrowing

### Pattern 1: Compositional Pipeline (Dataset -> Solver -> Scorer -> Metrics)

inspect_evals structures every evaluation as a four-stage pipeline where each component is independently swappable:

```
Dataset -> Solver chain -> Scorer -> Metrics
```

**How Snowl compares**: Snowl's current pipeline is `Adapter(sample) -> Agent -> Scorer`, which is similar but less flexible:
- No equivalent of `Solver` (composable processing steps that transform task state)
- Scorer output goes directly to artifact persistence, no metric aggregation layer
- No `task_with()` for programmatic override of pipeline components

**What to borrow**:
- **Solver chain concept**: Snowl's `ReActAgent` already does plan/act/observe, but the "solver" abstraction would allow composing prompt engineering, tool filtering, and defense strategies as reusable pipeline elements. This directly maps to AgentDojo's defense pipeline.
- **Metric layer**: After scoring, aggregate per-sample scores into benchmark-level metrics with stderr and grouped breakdowns.

### Pattern 2: Per-Eval Locality (ADR-0001)

inspect_evals moved from a central `listing.yaml` to per-eval `eval.yaml` files that live beside the implementation code:

```
src/inspect_evals/gpqa/
  gpqa.py          # Implementation
  eval.yaml        # Metadata, version, assets
```

**How Snowl compares**: Snowl uses a central `registry.py` for all benchmark metadata. Adding a new benchmark requires editing the registry file.

**What to borrow**:
- Each benchmark directory could contain a `benchmark.yaml` or similar metadata file
- Registry auto-discovers benchmarks by scanning directories
- Reduces merge conflicts and enables independent versioning

**But with caution**: Snowl's registry is currently simple and works well. Don't over-engineer this for 20 benchmarks.

### Pattern 3: Sandbox Isolation Per Sample

inspect_evals gives each sample its own sandbox instance:

```python
# Per-sample sandbox
sample = Sample(
    input="...",
    sandbox="docker",           # Use Docker
    files={"flag.txt": "..."},  # Files copied into sandbox
    setup="chmod +x /app/run",  # Setup script
)
```

**How Snowl compares**: Snowl's sandbox is per-trial (prepared in `prepare_trial_phase`), which is equivalent since each sample = one trial. But Snowl doesn't support per-sample `files` or `setup` scripts.

**What to borrow**:
- Per-sample file injection for benchmarks that need workspace setup
- This is particularly useful for AgentDojo, where injection vectors are placed in specific files

### Pattern 4: Deferred Scoring (Run without scoring, score later)

inspect_evals supports `--no-score` to skip scoring during generation, then `inspect score` to apply any scorer later:

```bash
inspect eval task.py --no-score
inspect score log.json --scorer model_graded_qa
```

**How Snowl compares**: Scoring is tightly coupled to execution in `score_trial_phase`. No way to skip scoring or rescore with a different scorer.

**What to borrow**:
- `--no-score` flag in `snowl eval`
- `snowl rescore <run_id>` command
- This enables iterative scorer development without re-running expensive agent trials

### Pattern 5: Eval Sets for Multi-Task Orchestration

inspect_evals provides `eval_set()` for running multiple tasks with multiple models:

```python
success, logs = eval_set(
    tasks=[task1, task2, task3],
    models=["openai/gpt-4", "anthropic/claude-3"],
    max_tasks=10,  # Parallel task execution
)
```

**How Snowl compares**: Snowl has `suite.yml` for multi-benchmark runs, but:
- No `max_tasks` parallelism across benchmarks
- No automatic retry of failed evaluations
- No re-use of completed samples from failed tasks

**What to borrow**:
- Cross-benchmark parallelism with `max_tasks`
- Better retry and recovery across suite runs

## 5.2 Patterns NOT Worth Borrowing

### N1: Decorator-Based Registration (`@task`, `@solver`, `@scorer`)

inspect_evals uses decorators for discovery. Snowl already has `@task`, `@agent`, `@scorer` decorators in `declarations.py`. The current approach works fine; no change needed.

### N2: AnyIO Backend Support

inspect_evals uses AnyIO for async backend flexibility (asyncio or Trio). Snowl uses asyncio directly, which is simpler and sufficient. Adding AnyIO would increase complexity without clear benefit.

### N3: N-X Versioning Scheme

inspect_evals uses an N-X versioning scheme (e.g., `2-B`) where N is result-compatibility and X is interface-compatibility. This is useful for a public benchmark repository but overkill for Snowl's internal framework.

### N4: Register System (External Evals)

inspect_evals' new Register system allows third-party evals to be discovered via YAML without submitting code. Snowl is not a public evaluation registry; this doesn't apply.

## 5.3 Key Architectural Differences

| Aspect | inspect_evals | Snowl | Recommendation |
|--------|--------------|-------|----------------|
| Scorer protocol | Async (`@scorer` returns async) | Sync | Adopt async (Phase 1) |
| Tool execution | Via `Solver` chain | Via `Agent.run(tools=...)` | Add `AsyncToolSpec` (Phase 2) |
| Metric aggregation | Built-in (`accuracy()`, `stderr()`) | None at scorer level | Add `MetricAggregator` (Phase 4) |
| Sandbox per sample | Yes, with files/setup | Per trial, no files | Add per-sample files (Phase 2) |
| Concurrency model | `max_samples`, `max_tasks`, `max_sandboxes`, `max_connections` | `max_running_trials`, `max_scoring_tasks`, `provider_budgets` | Add benchmark profiles (Phase 1) |
| Composition | `chain()`, `task_with()` | Manual in scorer code | Add composable scorer chain (Phase 1) |
| Deferred scoring | `--no-score` + `inspect score` | Not supported | Add in Phase 4 |
| Eval sets | `eval_set()` with multi-model | `suite.yml` | Enhance suite orchestration (Phase 4) |

## 5.4 Inspiration for ToolEmu-Specific Design

ToolEmu's LM-emulated sandbox is unique and doesn't have a direct equivalent in inspect_evals. However, the **solver chain** pattern is instructive:

```
Agent solver: generates tool call
  -> Emulation solver: intercepts tool call, generates observation
    -> Critique solver: validates observation format
  <- Observation returned to agent
```

This can be modeled in Snowl as a `ToolMiddleware` that wraps tool execution:

```python
class ToolMiddleware(Protocol):
    """Intercepts and optionally transforms tool calls and their results."""
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
        return result
```

This is more flexible than a dedicated `EmulatedToolWrapper` because:
1. It can be composed (emulation + injection + logging)
2. It works with both real and stub tools
3. It can be configured per-benchmark without code changes

**Recommendation**: Implement `ToolMiddleware` as the core abstraction, with `EmulatedToolWrapper` and `InjectionMiddleware` as specific implementations.

## 5.5 Inspiration for AgentDojo-Specific Design

AgentDojo's defense pipeline maps well to inspect_evals' solver chain concept:

```
SystemMessage -> InitQuery -> [Defense1] -> [Defense2] -> LLM -> ToolsExecutionLoop
```

In Snowl terms, this would be a `ReActAgent` with configurable middleware:

```python
agent = ReActAgent(
    client=llm,
    max_steps=15,
    middlewares=[
        RepeatUserPromptMiddleware(),      # defense: repeat user prompt
        SpotlightingMiddleware(),          # defense: delimit tool outputs
        TransformersPIDetectorMiddleware(), # defense: detect injection
    ],
)
```

Each middleware intercepts the agent's loop at specific points:
- Before agent LLM call: modify messages
- After agent LLM call: filter tool calls
- After tool execution: modify tool results

This is more modular than AgentDojo's pipeline and composes well with the `ToolMiddleware` pattern above.
