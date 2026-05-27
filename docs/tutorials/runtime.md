# Runtime Configuration

How to control evaluation execution: concurrency, middleware, containers, and resource budgets.

---

## RuntimePolicy

`RuntimePolicy` controls how trials are scheduled and how resources are allocated:

```python
from snowl.runtime.policy import RuntimePolicy

policy = RuntimePolicy()
resolution = policy.resolve(
    total_tasks=100,
    max_running_trials=6,
    concurrency_profile=None,  # or a BenchmarkConcurrencyProfile
)
```

### BenchmarkConcurrencyProfile

Benchmark-specific guidance for scheduling:

```python
from snowl.benchmarks.base import BenchmarkConcurrencyProfile

profile = BenchmarkConcurrencyProfile(
    name="toolemu",
    api_call_amplification=30.0,  # ~30 API calls per trial
    recommended_max_running=3,
    scorer_uses_provider=True,
    scorer_provider_id="openai",
)
```

Profiles are defined in benchmark registry entries. When running via `snowl eval`, the runtime automatically picks up the profile for the selected benchmark.

## Execution modes

| Mode | Description |
|------|-------------|
| `native` | Direct agent execution (default) |
| `emulated` | Tools emulated by an LLM |
| `stateful` | Stateful tool execution with real state |
| `stateful+injection` | Stateful tools + injection testing |
| `injection` | Injection attack middleware only |

Set in `project.yml`:

```yaml
execution_mode: emulated
middleware_config:
  emulator_model: gpt-4o-mini
```

## Tool middleware

Middleware intercepts tool calls and results. Built-in middleware:

- `PolicyEnforcementMiddleware` -- enforce tool call policies at runtime
- `EmulatedToolWrapper` -- simulate tool results with an LLM
- `StatefulToolExecutor` -- manage stateful tool environments

Add middleware to an agent:

```python
from snowl.tools.middleware import PolicyEnforcementMiddleware

agent.middlewares = [PolicyEnforcementMiddleware(policy=my_policy)]
```

See [Tool Middleware](tool-middleware.md) for the full tutorial.

## Container providers

Benchmarks that need Docker containers (OSWorld, TerminalBench) use container providers:

```python
from snowl.runtime.container_providers import ContainerProviderRegistry

registry = ContainerProviderRegistry()
registry.discover()  # loads providers from entry_points
```

Container providers are registered by snowl-evals via `entry_points`:

```toml
[project.entry-points."snowl.container_providers"]
osworld = "snowl_evals.osworld.provider:register_providers"
```

## Sandbox runtime

For tasks requiring sandboxed execution:

```python
from snowl.envs.sandbox_runtime import WarmPoolSandboxRuntime

sandbox = WarmPoolSandboxRuntime()
prepared = await sandbox.prepare(spec)
result = await sandbox.run(prepared, agent_run_fn)
await sandbox.teardown(prepared)
```

## MCP servers

Connect Model Context Protocol servers for tool discovery:

```yaml
# project.yml
mcp_servers:
  - name: airline_api
    transport: stdio
    command: python
    args: ["airline_server.py"]
```

MCP tools are automatically discovered and merged with project tools during trial preparation.

## Trial lifecycle

Each trial goes through four phases:

1. **Prepare** -- validate inputs, start containers, set up workspace, discover tools
2. **Execute** -- run the agent against the sample
3. **Score** -- apply scorer(s) to the trial result
4. **Finalize** -- tear down containers, sandbox, workspace; persist artifacts

```python
from snowl.runtime.engine import execute_trial, TrialRequest

outcome = await execute_trial(TrialRequest(
    task=task,
    agent=agent,
    sample=sample,
    scorer=my_scorer,
))
```

## Next steps

- [CLI](cli.md) -- running evaluations from the command line
- [Tool Middleware](tool-middleware.md) -- building custom middleware
- [Stateful Tool Execution](stateful-tool-execution.md) -- stateful environments
