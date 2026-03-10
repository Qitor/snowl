# Snowl

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl is an agent evaluation framework that is being hardened into an industrial-grade evaluation platform.

Its durable execution contract is:

- define `Task`
- define `Agent`
- define `Scorer`
- expand into `Task x AgentVariant x Sample`
- run with `snowl eval path/to/project.yml`

Everything else in the repo exists to make that contract reliable, observable, and scalable:

- benchmark adaptation
- multi-model sweeps
- provider-aware concurrency control
- container/runtime orchestration
- artifact persistence
- CLI + Web operator workflows

## Project Docs

- [START_HERE.md](./START_HERE.md): fastest repo orientation
- [ARCHITECTURE.md](./ARCHITECTURE.md): current system architecture and runtime direction
- [PLANS.md](./PLANS.md): roadmap and execution priorities
- [AGENTS.md](./AGENTS.md): repo rules for coding agents
- [docs/runtime_scheduling.md](./docs/runtime_scheduling.md): runtime scheduling design notes
- [docs/codex_best_practices.md](./docs/codex_best_practices.md): Codex guidance for this repo

## Current Product Shape

Snowl already supports:

- YAML-first project entrypoints via `project.yml`
- project-level multi-model authoring via `agent_matrix.models`
- benchmark adapters for:
  - `strongreject`
  - `terminalbench`
  - `osworld`
  - `toolemu`
  - `agentsafetybench`
- provider-aware local concurrency control
- container-aware execution for terminal / GUI benchmarks
- live artifacts under `.snowl/runs/`
- operator-focused Next.js Web monitor
- plain foreground CLI progress with background Web monitor sidecar
- resume and rerun-failed flows

Deployment target today is still local single-machine evaluation.

## Install

```bash
cd /Users/morinop/coding/snowl_v2
pip install -e .
```

This editable install also builds the bundled Web UI used by the packaged monitor.

## Prepare Reference Repos

Several official examples depend on external benchmark repos checked out under fixed paths:

- `references/terminal-bench`
- `references/OSWorld`
- `references/strongreject`
- `references/ToolEmu`
- `references/Agent-SafetyBench`

Example:

```bash
cd /Users/morinop/coding/snowl_v2
git clone <TERMINAL_BENCH_GIT_URL> references/terminal-bench
git clone <OSWORLD_GIT_URL> references/OSWorld
git clone <STRONGREJECT_GIT_URL> references/strongreject
git clone <TOOLEMU_GIT_URL> references/ToolEmu
git clone <AGENT_SAFETY_BENCH_GIT_URL> references/Agent-SafetyBench
```

## Quick Start

### Run an official example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official/project.yml
```

Other official examples:

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/toolemu-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/agentsafetybench-official/project.yml
```

### Run through a benchmark adapter

```bash
snowl bench list
```

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official/project.yml \
  --split test
```

## Default Runtime UX

The default CLI behavior is:

- foreground: plain terminal progress/logging for the eval itself
- background: auto-started Web monitor sidecar
- optional: `--cli-ui` enables the legacy live terminal UI

Typical flow:

```bash
snowl eval /absolute/path/to/my-project/project.yml
```

What happens:

1. the terminal prints project/run bootstrap details
2. the eval begins in the foreground
3. once the run is initialized, Snowl prints a Web URL such as `http://127.0.0.1:8765`
4. stopping the eval also stops that auto-started monitor sidecar

Useful flags:

- filtering: `--task`, `--agent`, `--variant`
- runtime budgets:
  - `--max-running-trials`
  - `--max-container-slots`
  - `--max-builds`
  - `--max-scoring-tasks`
  - `--provider-budget provider_id=n`
- reliability: `--resume`, `--rerun-failed-only`
- monitor: `--no-web-monitor`
- legacy live CLI: `--cli-ui`

Manual monitor mode is still available:

```bash
snowl web monitor --project /absolute/path/to/my-project --host 127.0.0.1 --port 8765
```

## `project.yml` Is The Source Of Truth

Snowl now treats one YAML file as the formal entrypoint for a run.

Recommended layout:

```text
my-project/
  project.yml
  task.py
  agent.py
  scorer.py
  tool.py        # optional
```

Example:

```yaml
project:
  name: strongreject-qwen-sweep
  root_dir: .

provider:
  id: siliconflow
  kind: openai_compatible
  base_url: https://api.siliconflow.cn/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: qwen25_7b
      model: Qwen/Qwen2.5-7B-Instruct
    - id: qwen3_32b
      model: Qwen/Qwen3-32B

judge:
  model: gpt-4.1-mini

eval:
  benchmark: strongreject
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
    tool_module: ./tool.py
  split: test
  limit: 50

runtime:
  max_running_trials: 8
  max_container_slots: 0
  max_builds: 2
  max_scoring_tasks: 8
  provider_budgets:
    siliconflow: 8
```

Key semantics:

- `project.root_dir`: project root for artifact placement and relative paths
- `eval.code.base_dir`: code loading root for `task.py`, `agent.py`, `scorer.py`, `tool.py`
- `provider`: the project's remote model provider
- `agent_matrix.models`: the tested models that expand into `AgentVariant`s
- `judge.model`: optional model-as-judge model, separate from the tested models
- `runtime.provider_budgets`: provider-level concurrency limits

The directory structure still matters; YAML just makes that structure explicit instead of implicit.

## Multi-Model Authoring

The recommended pattern in `agent.py` is:

```python
from pathlib import Path

from snowl.agents import build_model_variants
from snowl.core import agent


def build_agent_for_model(model_entry, provider_config):
    ...


@agent(agent_id="demo_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="demo_agent",
        factory=build_agent_for_model,
    )
```

This same pattern now powers both QA-style examples and container-heavy examples such as TerminalBench and OSWorld.

## Runtime Scheduling Model

Snowl is moving from coarse semaphores toward an explicit phase-aware scheduler.

Runtime controls now separate:

- `max_running_trials`: active agent execution
- `max_container_slots`: active container/sandbox capacity
- `max_builds`: expensive build/pull/setup work
- `max_scoring_tasks`: scoring concurrency
- `provider_budgets[provider_id]`: remote provider concurrency

Current runtime behavior already reflects two important architectural decisions:

- provider is the main concurrency boundary for remote model calls
- scoring is no longer forced to occupy the same execution slot as agent execution

That means QA workloads and container-heavy workloads can share one scheduler while consuming different budgets.

## Artifacts And Observability

Each run writes under:

```text
<project>/.snowl/runs/<run_id>/
```

Important artifacts include:

- `manifest.json`
- `plan.json`
- `summary.json`
- `aggregate.json`
- `profiling.json`
- `trials.jsonl`
- `events.jsonl`
- `run.log`

Observability surfaces:

- CLI: operator-friendly foreground progress/logging
- Web monitor:
  - `/`: run gallery / operator board
  - `/runs/[runId]`: single-run workspace
  - `/compare`: secondary historical comparison view

Running runs are expected to become visible immediately. Snowl writes bootstrap artifacts early so the Web monitor can show planned trials, visible tasks, models, and progress before the run completes.

## Examples

See [examples/README.md](./examples/README.md) for the convention used by official examples.

## Development Checks

Python tests:

```bash
pytest -q
```

Runtime-focused:

```bash
pytest -q tests/test_eval_autodiscovery.py tests/test_runtime_controls_and_profiling.py tests/test_resource_scheduler.py tests/test_cli_eval.py
```

Synthetic scheduler benchmark:

```bash
python scripts/runtime_scheduler_benchmark.py
```

Web UI typecheck:

```bash
cd webui
npm run -s typecheck
```

Packaged install sanity:

```bash
pip install -e .
```
