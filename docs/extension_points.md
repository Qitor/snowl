# Extension Points

How to extend Snowl with custom benchmarks, scorers, agents, and model providers.

---

## Benchmark Adapters

Create a new package under `snowl/benchmarks/<name>/` or `snowl_evals/<name>/`.

### In snowl (built-in)

1. Create `snowl/benchmarks/<name>/adapter.py` subclassing `BaseBenchmarkAdapter`
2. Implement: `_iter_rows()`, `_row_split()`, `_row_to_sample()`
3. Register in `snowl/benchmarks/registry.py` via `register_builtin_benchmarks()`

### In snowl-evals (plugin)

1. Create `snowl_evals/<name>/adapter.py` subclassing `BaseBenchmarkAdapter`
2. Register via `entry_points` in `pyproject.toml`:

```toml
[project.entry-points."snowl.benchmarks"]
my_benchmark = "snowl_evals.my_benchmark:register_benchmark"
```

3. Implement `register_benchmark(registry)` that calls `registry.register(info, adapter_class)`

See [custom-benchmark-adapter.md](./how-to/custom-benchmark-adapter.md) for a full walkthrough.

## Container Providers

For benchmarks requiring Docker containers (e.g., OSWorld, TerminalBench):

1. Implement `ContainerProvider` protocol (`prepare()`, `close()`, `describe_requirements()`)
2. Register via `entry_points` in `pyproject.toml`:

```toml
[project.entry-points."snowl.container_providers"]
my_benchmark = "snowl_evals.my_benchmark.provider:register_providers"
```

3. Implement `register_providers(registry)` that calls `registry.register("my_benchmark", MyProvider())`

## Scorers

1. Create a class with a `score()` method returning `dict[str, Score]`
2. For sync scorers wrapping async code, use `from snowl.scorer._sync_bridge import run_coro_sync`
3. For LLM-judge scorers, use `from snowl.scorer._prompt import render_judge_prompt`

```python
from snowl.core import Score, ScoreContext, TaskResult

class MyScorer:
    def score(self, task_result: TaskResult, trace, context: ScoreContext) -> dict[str, Score]:
        return {"accuracy": Score(value=1.0, explanation="Correct")}
```

## Framework Adapters

To connect an agent framework to Snowl:

1. Create `snowl/adapters/<framework>.py`
2. Implement `wrap()` and `unwrap()` for state conversion
3. Implement `wrap_tools()` for tool schema conversion
4. Add `quick_eval_<framework>()` convenience function

See [framework-adapter-onboarding.md](./how-to/framework-adapter-onboarding.md) for details.

## Model Providers

1. Create a class implementing `ChatModelClient` protocol from `snowl/model/base.py`
2. The protocol requires: `generate(messages, *, model, **kwargs) -> Any`
3. Place in `snowl/model/` or a separate package

## Tool Middleware

Tool middleware intercepts tool calls and results:

1. Implement `ToolMiddleware` protocol: `intercept_call()`, `intercept_result()`
2. Register on an agent via `agent.middlewares.append(my_middleware)`

Built-in middleware:
- `PolicyEnforcementMiddleware` — enforce tool call policies at runtime
- `EmulatedToolWrapper` — simulate tool results with an LLM
- `StatefulToolExecutor` — manage stateful tool environments

See [tool-middleware.md](./tutorials/tool-middleware.md) for details.

## Entry Point Groups

| Group | Purpose | Registration Function |
|-------|---------|----------------------|
| `snowl.benchmarks` | Benchmark adapters | `register_benchmark(registry)` |
| `snowl.container_providers` | Container providers | `register_providers(registry)` |
