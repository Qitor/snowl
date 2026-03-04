# Snowl

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl is a general agent evaluation framework built around a simple contract:

- define `Task`
- define `Agent`
- define `Scorer`
- run with one command: `snowl eval ...`

It is designed for both custom evals and benchmark adaptation, with container/runtime complexity handled by the framework as much as possible.

## What Snowl Solves

- Unified eval contract across very different benchmarks (QA, terminal, GUI)
- Agent + Task are both first-class evaluation objects
- Multi-metric scoring (including model-as-judge)
- Built-in benchmark adapters (`strongreject`, `terminalbench`, `osworld`)
- Research-friendly artifacts (`trials.jsonl`, `events.jsonl`, `metrics_wide.csv`, diagnostics)
- Live interactive CLI for long-running experiments

## Core Roadmap

1. Adapt more benchmarks: expand first-party adapters for additional widely used agent benchmarks.
2. Faster concurrency in runtime/engine: improve scheduling, parallelism, and throughput for large-scale evaluation runs.
3. Complete Web UI: deliver a full web-based experience for run monitoring, drill-down, and result comparison.
4. Support more agent frameworks: add adapters/integration paths for more external agent ecosystems.
5. More built-in evaluation toolkits: add richer built-in scorer/tool packs for common eval patterns.

## Current Status (P0 + P1 Mainline)

Implemented in this repo now:

- Core contracts: `Task`, `Agent`, `Scorer`, `ToolSpec`, `EnvSpec`, `TaskResult`
- Decorators: `@task`, `@agent`, `@scorer`, `@tool`
- Built-in agents: `ChatAgent`, `ReActAgent`
- Built-in scorer library: text-match family, model-as-judge, composition, unit-test scorer
- Benchmark adapters: `strongreject`, `terminalbench`, `osworld`
- Container-aware runtime orchestration (`ContainerRuntime`) for terminal/gui benchmarks
- Live CLI + run artifacts + resume/rerun-failed support

## Quick Start

## 1) Prepare benchmark references (required)

Snowl expects benchmark sources under `references/` with fixed folder names:

- `references/terminal-bench`
- `references/OSWorld`
- `references/strongreject`

From repo root:

```bash
cd /Users/morinop/coding/snowl_v2
git clone <TERMINAL_BENCH_GIT_URL> references/terminal-bench
git clone <OSWORLD_GIT_URL> references/OSWorld
git clone <STRONGREJECT_GIT_URL> references/strongreject
```

If your team uses internal mirrors, replace the URLs but keep the target directories unchanged.

## 2) Create conda environment and install

```bash
cd /Users/morinop/coding/snowl_v2
conda create -n snowl python=3.11 -y
conda activate snowl
pip install -U pip
pip install -e .
```

Or run without install:

```bash
python -m snowl.cli --help
```

## 3) Run an Example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official
```

## 4) Run via Benchmark Adapter

```bash
snowl bench list
```

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official \
  --split test
```

## One-Click Eval Folder Contract

Snowl is designed so users can package an eval target in one folder and run it directly.

Recommended minimal layout:

```text
my-eval/
  task.py
  agent.py
  scorer.py
  model.yml        # optional
  tool.py          # optional
  panels.yml       # optional (UI panel override)
```

Then run:

```bash
snowl eval /absolute/path/to/my-eval
```

Discovery contract:

- `task.py` exports one or more `Task` objects/factories
- `agent.py` exports one or more `Agent` / `AgentVariant` objects/factories
- `scorer.py` exports scorer object/factory
- `tool.py` is optional and can auto-register tools via `@tool`

For benchmark mode:

- adapter loads benchmark tasks
- your project folder still provides agent/scorer/tool
- run with `snowl bench run <benchmark> --project <your-folder> ...`

## Automatic Matrix Expansion (Core Eval Idea)

Snowl plan expansion is designed around matrix execution rather than manual scripting.

Conceptual target matrix:

- `Task x AgentVariant x Scorer x Sample`

Current implementation status:

- automatic: `Task x AgentVariant x Sample`
- scorer execution: one active scorer per run (first discovered scorer object)
- multi-metric in one run: supported via one scorer returning multiple metric keys

Practical recommendation today:

1. Use multiple agents/variants in `agent.py` and let Snowl auto-expand compare runs.
2. Put related metrics into one scorer output map (e.g. `accuracy`, `safety`, `latency_score`).
3. If you need strict scorer-isolation comparison now, run separate evals with scorer filtering/export conventions.

Roadmap direction:

- first-class `Task x AgentVariant x Scorer` expansion so multiple scorers can be compared in one orchestrated run.

Planning mode examples:

- `1 Task x 1 AgentVariant` -> single
- `N Task x 1 AgentVariant` -> task_sweep
- `1 Task x M AgentVariant` -> compare
- `N Task x M AgentVariant` -> matrix

## Authoring Patterns (Decorator-First)

Snowl supports two discovery patterns:

1. Decorator-first (recommended)
2. Fallback object discovery (compatibility)

Decorator-first examples:

```python
from snowl.core import task, agent, scorer, Task, EnvSpec, Score

@task(task_id="demo:test")
def build_task():
    return Task(
        task_id="demo:test",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([{"id": "s1", "input": "hello"}]),
    )

@agent(agent_id="demo_agent")
class DemoAgent:
    async def run(self, state, context, tools=None):
        state.output = {"message": {"role": "assistant", "content": "ok"}}
        return state

@scorer(scorer_id="demo_scorer")
class DemoScorer:
    def score(self, task_result, trace, context):
        return {"pass": Score(value=1.0)}
```

Why decorators are preferred:

- explicit identity (`task_id`, `agent_id`, `scorer_id`)
- deterministic discovery order
- lower boilerplate in examples and benchmark ports
- easier static review for maintainers

## Runtime / Env / Tool Design Rationale

Snowl intentionally separates evaluation orchestration from environment mechanics.

Core ideas:

1. `Task + Agent + Scorer` as stable contracts.
2. `TaskResult` has fixed core fields and extensible `payload`.
3. tools declare `required_ops`; env declares `provided_ops`; runtime checks compatibility before execution.
4. heavy environment logic is centralized in runtime/env layers, not leaked to end-user task authoring.

`EnvSpec` design intent:

- `env_type` indicates execution domain (`local`, `terminal`, `gui`, ...)
- `provided_ops` defines capability surface
- optional `sandbox_spec` captures container/sandbox requirements

Tool-env safety rule:

- if tool requires ops not provided by env, trial fails fast with explicit preflight error

Runtime layering:

- planner (`eval.py`) expands trials
- trial engine (`runtime/engine.py`) executes one trial
- container orchestration (`runtime/container_runtime.py`) handles benchmark container lifecycle
- concrete command/action execution lives in env implementations (`envs/`)

Why this matters:

- benchmark authors can focus on task loading and scoring semantics
- agent authors can focus on behavior, not compose lifecycle scripts
- maintainers can optimize runtime centrally (parallelism, retries, logging, diagnostics)

## Model Configuration

Snowl supports OpenAI-compatible model config from either env vars or `model.yml`.

Example `model.yml`:

```yaml
openai_compatible:
  base_url: https://api.siliconflow.cn/v1
  api_key: sk-...
  model: Qwen/Qwen3-32B
  timeout: 30
  max_retries: 2
```

Resolution precedence:

1. explicit environment variables (`OPENAI_*`)
2. `model.yml` / `model.yaml`

So env vars can always override local file settings.

## CLI Overview

Main commands:

- `snowl eval <path>`: auto-discover `task.py/agent.py/scorer.py/tool.py` and run
- `snowl bench run <benchmark> --project <example_dir>`: load benchmark tasks + local agent/scorer
- `snowl bench list`: list adapters
- `snowl bench check <benchmark>`: adapter conformance checks
- `snowl examples check [examples_dir]`: validate example layout

Useful eval flags:

- filtering: `--task`, `--agent`, `--variant`
- runtime limits: `--max-trials`, `--max-sandboxes`, `--max-builds`, `--max-model-calls`
- reliability: `--resume`, `--rerun-failed-only`
- UI: `--no-ui`, `--ui-mode`, `--ui-theme`, `--ui-refresh-profile`

## Project Architecture

The architecture follows `Task + Agent + Scorer` as the core eval unit (`Task x AgentVariant x Sample`).

```text
                         +----------------------+
task.py ---------------->|                      |
agent.py --------------->|      Eval Planner    |
scorer.py -------------->|                      |
tool.py (optional) ----->|                      |
                         +----------+-----------+
                                    |
                                    v
                         +----------+-----------+
                         |      Runtime Engine  |
                         +----+-----+-----+-----+
                              |     |     |
                              |     |     +------------------------+
                              |     |                              |
                              v     v                              v
                  +-----------+--+  +-------------+     +----------+-----------+
                  |ContainerRuntime| |SandboxRuntime|    |      Agent.run      |
                  +-----------+--+  +-------------+     +----------+-----------+
                                                                  |        |
                                                                  v        v
                                                         +--------+--+  +--+------+
                                                         |Model Client|  | Tools  |
                                                         +-----------+  +---------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |  TaskResult+Trace  |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |    Scorer.score    |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |       Metrics      |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |      Aggregator    |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         | Artifacts + Live UI|
                                                         +--------------------+
```

## Layered Module Map

- `snowl/core/`
- Protocols and contracts (`Task`, `Agent`, `Scorer`, `EnvSpec`, `ToolSpec`, `TaskResult`)
- Decorators for autodiscovery

- `snowl/eval.py`
- Project autodiscovery
- Eval planning and orchestration
- checkpoint/resume/rerun-failed
- artifact writing and run logging

- `snowl/runtime/`
- Trial execution engine (`execute_trial`)
- Shared `ContainerRuntime` for benchmark container lifecycle

- `snowl/envs/`
- Concrete env implementations (`TerminalEnv`, `GuiEnv`, sandbox runtime)
- Docker compose command execution and streaming hooks

- `snowl/model/`
- OpenAI-compatible model client
- timeout/retry/error formatting

- `snowl/scorer/`
- Shared scorer building blocks (text, model judge, composition, unit-test)

- `snowl/benchmarks/`
- Benchmark adapters and registry
- currently: `strongreject`, `terminalbench`, `osworld`, plus generic `jsonl/csv`

- `snowl/ui/`
- Live CLI renderer, controls, panel system

- `snowl/aggregator/`
- Cross-trial metric aggregation and schema metadata

## Runtime Execution Model

For each trial:

1. Validate `Task/Agent/Scorer/EnvSpec`
2. Build agent context from sample + task metadata
3. Prepare environment/container if required (via `ContainerRuntime`)
4. Run `agent.run(...)`
5. Build `TaskResult` + trace
6. Run scorer to produce metric map
7. Emit live events and append logs/artifacts

For docker-like tasks, Snowl enforces safer defaults (e.g. serial/low parallelism) and exposes build/start/stop diagnostics through event stream and log files.

## Artifacts and Observability

Every run writes to:

- `<project>/.snowl/runs/<timestamp>/`
- `<project>/.snowl/runs/by_run_id/run-...` (symlink/pointer to run dir)

Main outputs:

- `run.log`: append-first full runtime log
- `plan.json`, `summary.json`, `aggregate.json`, `outcomes.json`
- `trials.jsonl`: one JSON row per trial result
- `events.jsonl`: event stream rows
- `metrics_wide.csv`: flattened metrics table
- `diagnostics/*.json` + `diagnostics_index.json`
- `report.html`
- `profiling.json`

This layout is designed for both human debugging and downstream research analysis pipelines.

## Extension Guide

## Add a New Agent

Place in your example or library code:

```python
from snowl.core import agent

@agent(agent_id="my_agent")
class MyAgent:
    async def run(self, state, context, tools=None):
        ...
        return state
```

Or export multiple variants with `make_agent_variant(...)` and filter by `--variant`.

## Add a New Task

```python
from snowl.core import Task, EnvSpec, task

@task(task_id="my_task:test")
def build_task():
    return Task(
        task_id="my_task:test",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([{"id": "s1", "input": "hello"}]),
        metadata={"benchmark": "my_task"},
    )
```

## Add a New Scorer

```python
from snowl.core import scorer, Score

@scorer(scorer_id="my_scorer")
class MyScorer:
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
```

## Add a Tool with Auto Schema

```python
from snowl.core import tool

@tool(required_ops=("terminal.exec",))
def run_cmd(cmd: str) -> str:
    """Run shell command.

    Args:
      cmd: Command to execute.
    """
    ...
```

`@tool` will parse signature/docstring and auto-register into default `ToolRegistry`.

## Add a New Benchmark Adapter

Create `snowl/benchmarks/<name>/adapter.py` implementing adapter contract similar to existing ones:

- expose `info`
- implement `list_splits()`
- implement `load_tasks(split, limit, filters) -> list[Task]`
- map benchmark rows to Snowl `Task` samples
- keep benchmark-specific quirks minimal; preserve task loading and scoring semantics

Then register in `snowl/benchmarks/registry.py`.

## Example System Convention

All runnable examples are top-level under `examples/` (not under `snowl/`):

```text
examples/
  <example_name>/
    task.py
    agent.py
    scorer.py
    tool.py      # optional
    model.yml    # optional
```

Run:

```bash
snowl eval examples/<example_name>
```

## Built-in Benchmarks in This Repo

- `strongreject`
- No container path
- dataset from `references/strongreject/...`

- `terminalbench`
- terminal + docker compose path
- task metadata includes compose/test assets

- `osworld`
- GUI/container path
- env and action-loop integration via Snowl runtime

## Testing and Development

Run tests:

```bash
pytest -q
```

Targeted tests:

```bash
pytest -q tests/test_live_cli_p1.py
pytest -q tests/test_terminalbench_benchmark.py
```

Validate examples layout:

```bash
snowl examples check /Users/morinop/coding/snowl_v2/examples
```

## Maintenance Notes

- Prefer changing shared logic in `snowl/` over adding wrappers in `examples/`.
- Keep benchmark-specific code inside `snowl/benchmarks/<name>/`.
- Keep shared scoring primitives in `snowl/scorer/`.
- Keep event names and artifact schema stable; downstream analysis relies on them.
- For long-running/container debugging, always check `run.log` and `events.jsonl` first.

## Related Docs in This Repo

- `/Users/morinop/coding/snowl_v2/DESIGN.md`
- `/Users/morinop/coding/snowl_v2/task_p0.md`
- `/Users/morinop/coding/snowl_v2/task_p1.md`
- `/Users/morinop/coding/snowl_v2/todo_list.md`
- `/Users/morinop/coding/snowl_v2/todo_list_p1.md`
- `/Users/morinop/coding/snowl_v2/ui_tasks.md`
- `/Users/morinop/coding/snowl_v2/ux_next.md`

---

If you are onboarding as a maintainer, start with:

1. `snowl/cli.py` (entrypoints)
2. `snowl/eval.py` (discovery/planning/artifacts)
3. `snowl/runtime/engine.py` + `snowl/runtime/container_runtime.py`
4. one benchmark adapter (`snowl/benchmarks/terminalbench/adapter.py`)
5. one example (`examples/terminalbench-official/`)

This path gives you the fastest end-to-end mental model.
