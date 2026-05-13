# Snowl Tutorials

A hands-on guide to evaluating AI agent safety with Snowl.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Project Anatomy](#2-project-anatomy)
3. [Running Evaluations](#3-running-evaluations)
4. [Writing Your Own Agent](#4-writing-your-own-agent)
5. [Writing a Custom Task](#5-writing-a-custom-task)
6. [Writing a Custom Scorer](#6-writing-a-custom-scorer)
7. [Tool Middleware](#7-tool-middleware)
8. [Stateful Tool Execution](#8-stateful-tool-execution)
9. [Built-in Benchmarks](#9-built-in-benchmarks)
10. [Creating a New Benchmark Adapter](#10-creating-a-new-benchmark-adapter)
11. [Multi-Model Sweeps](#11-multi-model-sweeps)
12. [Run Artifacts](#12-run-artifacts)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Quick Start

### Install

```bash
pip install -e .
```

### Run a built-in benchmark

```bash
# List available benchmarks
snowl bench list

# Run StrongReject with default settings
snowl eval examples/strongreject-official/project.yml

# Run ToolEmu emulation eval
snowl eval examples/toolemu-emulation/project.yml

# Run with a limit (faster for testing)
snowl eval examples/strongreject-official/project.yml --limit 5
```

That's it. You'll see a Rich-panel TUI with colored progress, model I/O, and scorer results scrolling in your terminal.

---

## 2. Project Anatomy

Every Snowl evaluation project is a directory with four files:

```
my-project/
  project.yml    # Configuration: provider, models, benchmark, runtime
  agent.py       # Agent definition: how the agent is constructed
  task.py        # Task definition: what benchmark to load
  scorer.py      # Scorer definition: how to score agent outputs
```

### project.yml

The central configuration file:

```yaml
project:
  name: my-eval

provider:
  id: my-provider
  kind: openai_compatible
  base_url: https://api.example.com/v1
  api_key: sk-xxx
  timeout: 120

agent_matrix:
  models:
    - id: my_model
      model: my-model-v1
      metadata:
        company: acme
        source_type: open_source

eval:
  benchmark: strongreject
  split: test
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
  limit: 10

runtime:
  max_running_trials: 2
  provider_budgets:
    my-provider: 100
```

Key sections:
- **provider**: LLM API endpoint configuration (OpenAI-compatible)
- **agent_matrix.models**: List of model variants to evaluate
- **eval**: Which benchmark, where the code is, sample limits
- **runtime**: Concurrency limits and provider budgets

---

## 3. Running Evaluations

### Basic eval

```bash
snowl eval path/to/project.yml
```

### Common flags

```bash
# Limit samples
snowl eval project.yml --limit 5

# No TUI output (for scripts/CI)
snowl eval project.yml --no-ui

# Legacy full-screen dashboard
snowl eval project.yml --cli-ui

# Custom runtime concurrency
snowl eval project.yml --max-running-trials 4

# Resume a previous run
snowl eval project.yml --resume <run_id>

# Rerun only failed trials
snowl eval project.yml --rerun-failed-only

# Provider budget
snowl eval project.yml --provider-budget my-provider=50
```

### Benchmark commands

```bash
# List all built-in benchmarks
snowl bench list

# Run a built-in benchmark directly
snowl bench run strongreject --project project.yml

# Scaffold a new benchmark adapter
snowl bench scaffold my-benchmark --out ./my-benchmark

# Validate a benchmark adapter
snowl bench check my-benchmark --adapter ./adapter.py:MyAdapter
```

### Retry unfinished runs

```bash
snowl retry <run_id>
```

---

## 4. Writing Your Own Agent

An agent is any object with:
- `agent_id: str` — unique identifier
- `async def run(self, state, context, tools=None) -> AgentState` — execution loop

### Minimal agent

```python
# agent.py
from snowl.core import agent as declare_agent, AgentState, AgentContext

class MyAgent:
    agent_id = "my_agent"

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        state.output = {"message": "Hello from my agent!"}
        state.stop_reason = "completed"
        return state

@declare_agent(agent_id="my_agent")
def agents():
    return [MyAgent()]
```

### ReAct agent with tools

The built-in `ReActAgent` runs a Plan-Act-Observe loop with LLM-powered tool calling:

```python
# agent.py
from snowl.agents import ReActAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, ProjectModelEntry, ProjectProviderConfig

def _build_react_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig):
    client = OpenAICompatibleChatClient(model_entry.config)
    return ReActAgent(
        model_client=client,
        agent_id="react_agent",
        max_steps=10,
    )

@declare_agent(agent_id="react_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="react_agent",
        factory=_build_react_agent,
    )
```

### Agent with ToolMiddleware

Inject middleware into `ReActAgent` to intercept tool calls:

```python
from snowl.tools.middleware import LoggingMiddleware
from snowl.agents import ReActAgent

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
    max_steps=8,
)
```

### AgentState fields

| Field | Type | Purpose |
|-------|------|---------|
| `messages` | `list[dict]` | Conversation history |
| `actions` | `list[Action]` | Tool calls made |
| `observations` | `list[Observation]` | Tool results received |
| `output` | `dict | None` | Final output payload |
| `stop_reason` | `StopReason | None` | Why the agent stopped |

---

## 5. Writing a Custom Task

A task defines what benchmark samples to load:

```python
# task.py
from snowl.core import task as declare_task, Task
from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.project_config import load_project_config

PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = StrongRejectBenchmarkAdapter()
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit,
    )
```

`load_single_task` is a convenience wrapper. For more control, use the adapter directly:

```python
@declare_task()
def task() -> Task:
    adapter = MyBenchmarkAdapter(dataset_path="data.json")
    tasks = adapter.load_tasks(split="official", limit=10, filters={"suite": "banking"})
    return tasks[0]
```

---

## 6. Writing a Custom Scorer

A scorer evaluates agent outputs and produces numeric scores:

### Simple sync scorer

```python
# scorer.py
from snowl.core import Scorer, Score, ScoreContext, TaskResult

class MyScorer:
    scorer_id = "my_scorer"

    def score(self, task_result: TaskResult, trace: dict, context: ScoreContext) -> dict[str, Score]:
        output = task_result.final_output or ""
        is_safe = "dangerous" not in output.lower()
        return {
            "safety": Score(value=1.0 if is_safe else 0.0, explanation="Output safety check"),
        }

scorer = MyScorer()
```

### Async scorer (for LLM-based judging)

```python
from snowl.core import AsyncScorer, Score, ScoreContext, TaskResult

class MyLLMJudge:
    scorer_id = "llm_judge"

    async def ascore(self, task_result: TaskResult, trace: dict, context: ScoreContext) -> dict[str, Score]:
        # Use an LLM to judge the output
        client = OpenAICompatibleChatClient(config)
        response = await client.generate([{"role": "user", "content": f"Rate this: {task_result.final_output}"}])
        return {
            "quality": Score(value=0.8, explanation=response.message.get("content", "")),
        }
```

### Composable scorers

Snowl provides built-in composable scorers:

```python
from snowl.scorer import checkpoint_score, state_transition, tool_trace_policy

# State transition: checks if state changed as expected
utility = state_transition(metric_name="utility")

# Tool trace policy: checks if agent called forbidden tools
security = tool_trace_policy(metric_name="security")

# Checkpoint: weighted composite of other scores
composite = checkpoint_score(
    metric_name="overall",
    weights={"utility": 0.5, "security": 0.5},
)
```

---

## 7. Tool Middleware

Tool middleware intercepts tool calls and results, enabling powerful patterns like logging, emulation, and stateful execution.

### The ToolMiddleware protocol

```python
class ToolMiddleware(Protocol):
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""
        ...

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
        ...
```

### MiddlewareChain

Middlewares are composed in a `MiddlewareChain`:
- **Calls** flow forward: M1.intercept_call → M2.intercept_call → tool
- **Results** flow backward: tool → M2.intercept_result → M1.intercept_result

### Built-in middlewares

| Middleware | Purpose |
|-----------|---------|
| `LoggingMiddleware` | Records all calls and results to `.log` |
| `IdentityMiddleware` | No-op pass-through (for testing) |
| `EmulatedToolWrapper` | Replaces tool results with LM-emulated observations |
| `StatefulToolExecutor` | Replaces sentinel stubs with real stateful execution |

### Custom middleware example

```python
from snowl.tools.middleware import ToolMiddleware

class TruncateMiddleware:
    """Truncate long tool results."""

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args  # passthrough

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        if isinstance(result, str) and len(result) > 500:
            return result[:500] + "... (truncated)"
        return result
```

Wire it into an agent:

```python
agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware(), TruncateMiddleware()],
)
```

---

## 8. Stateful Tool Execution

For benchmarks like AgentDojo where tools mutate shared state across calls, Snowl provides `StatefulToolExecutor`:

### How it works

1. Stub tools return `{"__stateful__": True}` (the sentinel)
2. `StatefulToolExecutor.intercept_result()` detects the sentinel
3. Delegates to a real Python implementation that mutates a state dict
4. Returns the actual result instead of the sentinel

### Banking example

```python
from snowl.tools.stateful_executor import StatefulToolExecutor, make_stateful_stub_tool

# Create executor with initial state
executor = StatefulToolExecutor(
    suite="banking",
    initial_state={
        "bank_account": {"balance": 1000.0, "iban": "DE89...", "transactions": []},
        "user_account": {"first_name": "Emma", "password": "pass123"},
    },
)

# Create stub tools from OpenAI schemas
stub = make_stateful_stub_tool("get_balance", "Get balance", {"type": "object", "properties": {}})

# Wire into ReActAgent
agent = ReActAgent(model_client=client, middlewares=[executor], max_steps=10)

# After agent runs, inspect state changes
post_state = executor.get_post_state()
state_diff = executor.get_state_diff()  # list of {path, op, value}
```

### Available suites

| Suite | Tools | Description |
|-------|-------|-------------|
| `banking` | 11 tools | Balance, transactions, payments, file I/O, user account |
| `travel` | 18 tools | Hotels, restaurants, car rental, flights, reservations |

---

## 9. Built-in Benchmarks

Snowl ships with 20+ benchmark adapters:

| Benchmark | Domain | Type | Primary Metric |
|-----------|--------|------|----------------|
| `strongreject` | Agent safety | Safety | strongreject (lower=better) |
| `toolemu` | Agent safety | Safety | risk_rate (lower=better) |
| `agentdojo` | Agent safety | Safety | agentdojo_score (higher=better) |
| `agentharm` | Agent safety | Safety | agentharm_safety (higher=better) |
| `mask` | Agent safety | Safety | mask_score (lower=better) |
| `xstest` | Agent safety | Safety | xstest_safety (higher=better) |
| `bfcl` | Agent capability | Capability | function_call_accuracy |
| `terminalbench` | Cyber | Capability | pass_rate |
| `osworld` | Cyber | Capability | success_rate |
| `wmdp-cyber` | Cyber | Capability | accuracy |
| `wmdp-chem` | Chemical | Capability | accuracy |
| `sec_qa_v1/v2` | Cyber | Capability | accuracy |

Run any of them:

```bash
snowl bench run <benchmark-name> --project project.yml
```

---

## 10. Creating a New Benchmark Adapter

### Scaffold

```bash
snowl bench scaffold my-benchmark --out ./my-benchmark
```

### Implement the adapter

```python
# my-benchmark/adapter.py
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.base import BenchmarkInfo

class MyBenchmarkAdapter(BaseBenchmarkAdapter[dict]):
    name: str = "my_benchmark"
    description: str = "My custom benchmark"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            display_name="My Benchmark",
            domain="agentic_safety",
            benchmark_type="safety",
            primary_metric="safety_score",
            higher_is_better=True,
        )

    def _row_to_sample(self, row, *, row_index, row_split, selected_count):
        return {
            "id": f"my-bench-{row_index}",
            "input": row["prompt"],
            "metadata": {"split": row_split, **row.get("metadata", {})},
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
```

### Validate

```bash
snowl bench check my-benchmark --adapter ./my-benchmark/adapter.py:MyBenchmarkAdapter
```

---

## 11. Multi-Model Sweeps

Add multiple models to `agent_matrix.models` to evaluate them side by side:

```yaml
agent_matrix:
  models:
    - id: glm51
      model: glm-5.1-w4a8
      metadata:
        company: zhipu
        source_type: open_source
    - id: qwen3
      model: Qwen/Qwen3-32B
      metadata:
        company: alibaba
        source_type: open_source
    - id: gpt4o
      model: gpt-4o-2024-05-13
      provider:           # per-model provider override
        base_url: https://api.openai.com/v1
        api_key: sk-xxx
```

Snowl creates a trial for every (task x model x sample) combination. Results are aggregated in the Compare panel with ranked metric values.

---

## 12. Run Artifacts

Each eval run produces a directory under `.snowl/runs/`:

```
.snowl/runs/20260513T040647Z/
  manifest.json          # Run metadata (project, models, timestamps)
  plan.json              # Trial plan (task x agent x sample matrix)
  events.jsonl           # Stream of all runtime events
  attempts.jsonl         # Per-trial attempt records
  outcomes.json          # Final outcomes for all trials
  aggregate.json         # Aggregated metrics by task/agent
  leaderboard_rows.jsonl # Ranked rows for the compare view
  metrics_wide.csv       # Flat CSV of all metrics
  run.log                # Human-readable log
  report.html            # HTML report
```

### Key files

- **outcomes.json**: Maps trial keys to `{status, final_output, scores, usage, timing}`
- **aggregate.json**: Per (task, agent) metric averages and counts
- **events.jsonl**: Line-delimited JSON of all runtime events (model I/O, tool calls, scorer runs)

---

## 13. Troubleshooting

### "Model name shows as ?"

This happens when event metadata is nested under `payload`. The `_pick()` helper resolves this by checking `event[key]` → `event["payload"][key]` → `event["payload"]["payload"][key]`. If you see `?` in the TUI, ensure your events include the expected keys at one of these levels.

### "All trials error"

Check `run.log` for the error. Common causes:
- Invalid API key or base URL
- Model name not found at the provider
- Timeout too low for slow models (increase `provider.timeout`)

### "No samples loaded"

Ensure your task adapter's `dataset_path` points to an existing file and the file contains a JSON array with `prompt`/`input` fields.

### Rich panels look broken

Snowl uses Rich for terminal rendering. If panels look wrong:
- Ensure your terminal supports ANSI escape codes
- Try `--no-ui` for plain text output
- Set `TERM=xterm-256color` for better color support
