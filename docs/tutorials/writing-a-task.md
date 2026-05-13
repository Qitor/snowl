# Writing a Task

A task defines what benchmark samples to load and what environment they need.

---

## Using a built-in adapter

The simplest approach uses `load_single_task` with a built-in benchmark adapter:

```python
from pathlib import Path
from snowl.core import task as declare_task, Task
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.benchmarks.example_task import load_single_task
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

## Using an adapter directly

For more control over filtering and sample selection:

```python
@declare_task()
def task() -> Task:
    adapter = AgentDojoBenchmarkAdapter(
        suite="banking",
        with_injections=True,
    )
    tasks = adapter.load_tasks(
        split="official",
        limit=10,
        filters={"suite": "banking"},
    )
    return tasks[0]
```

## Adapter configuration

Most adapters accept configuration parameters:

```python
# AgentDojo: filter by suite and injection mode
adapter = AgentDojoBenchmarkAdapter(
    suite="travel",
    suites=["banking", "travel"],
    with_injections=True,
)

# ToolEmu: custom dataset path
adapter = ToolEmuBenchmarkAdapter(dataset_path="custom_toolemu.json")

# Generic JSONL adapter
adapter = JsonlBenchmarkAdapter(dataset_path="my_data.jsonl")
```

## The Task object

A `Task` contains:

| Field | Type | Purpose |
|-------|------|---------|
| `task_id` | `str` | Unique task identifier |
| `env_spec` | `EnvSpec` | Environment requirements |
| `sample_iter_factory` | `Callable` | Factory that returns a sample iterator |
| `metadata` | `dict` | Task-level metadata |

### Sample format

Each sample yielded by the iterator should be a dict with:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable sample identifier |
| `input` | Yes* | Prompt text (or use `messages`) |
| `messages` | Yes* | Chat-formatted messages |
| `metadata` | No | Sample metadata (passed to scorer context) |

*One of `input` or `messages` is required.

### Sample metadata

Metadata is passed to both the agent (via `AgentContext`) and the scorer (via
`ScoreContext`). Common metadata fields:

| Field | Description |
|-------|-------------|
| `split` | Dataset split name |
| `suite` | Benchmark suite (for multi-suite adapters) |
| `tool_schemas` | OpenAI-style tool schemas for dynamic tools |
| `tool_names` | Names of tools available for this sample |
| `target` | Expected output for scorer comparison |
| `category` | Sample category for grouped metrics |

## EnvSpec

The `EnvSpec` declares what environment the task needs:

```python
from snowl.core import EnvSpec, SandboxSpec

# Local execution (default)
env_spec = EnvSpec(env_type="local")

# Docker sandbox
env_spec = EnvSpec(
    env_type="sandbox",
    sandbox_spec=SandboxSpec(
        provider="docker",
        image="ubuntu:22.04",
    ),
)
```

| Field | Type | Description |
|-------|------|-------------|
| `env_type` | `str` | `"local"`, `"sandbox"`, `"terminal"`, `"gui"` |
| `provided_ops` | `tuple[str, ...]` | Operations the environment provides |
| `sandbox_spec` | `SandboxSpec \| None` | Container configuration |
| `config` | `dict` | Additional environment configuration |
