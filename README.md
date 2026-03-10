# Snowl

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl is an agent evaluation framework that is trying to grow into an industrial-grade evaluation platform.

Its core contract is intentionally small:

- define `Task`
- define `Agent`
- define `Scorer`
- run with `snowl eval ...`

Everything else is platform work around that core:

- benchmark adaptation
- multi-model expansion
- runtime orchestration
- container lifecycle management
- scoring and aggregation
- artifacts and observability
- Web-based run monitoring

## Project Docs

- [START_HERE.md](./START_HERE.md): fastest repo orientation
- [ARCHITECTURE.md](./ARCHITECTURE.md): current system architecture and industrialization direction
- [PLANS.md](./PLANS.md): product and engineering roadmap
- [AGENTS.md](./AGENTS.md): repo operating rules for coding agents
- [docs/codex_best_practices.md](./docs/codex_best_practices.md): Codex guidance for this repo

## What Snowl Supports Today

Snowl already has a real shared platform layer, not just one-off benchmark scripts.

Current product shape:

- custom eval folders via `snowl eval <path>`
- benchmark adapters via `snowl bench run <benchmark> --project <path>`
- project-level model matrix authoring via `model.yml`
- built-in benchmark coverage:
  - `strongreject`
  - `terminalbench`
  - `osworld`
  - `toolemu`
  - `agentsafetybench`
- live artifacts under `.snowl/runs/`
- Next.js Web monitor with run gallery, run workspace, SSE runtime logs, and compare view
- container-aware execution for terminal / GUI benchmarks
- resume and rerun-failed flows

Current deployment target is local single-machine evaluation with strong observability.

## Quick Start

### 1. Install

```bash
cd /Users/morinop/coding/snowl_v2
pip install -e .
```

This install also builds the bundled Web UI.

### 2. Prepare benchmark references

Some official examples depend on external benchmark repos checked out under fixed paths:

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

### 3. Run an example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official
```

Other official examples:

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official
snowl eval /Users/morinop/coding/snowl_v2/examples/toolemu-official
snowl eval /Users/morinop/coding/snowl_v2/examples/agentsafetybench-official
```

### 4. Run through a benchmark adapter

```bash
snowl bench list
```

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official \
  --split test
```

## Default Runtime UX

The default CLI behavior is now:

- foreground: plain terminal progress / logging for the eval itself
- background: auto-started Web monitor sidecar
- optional: `--cli-ui` enables the legacy live CLI panels

Typical flow:

```bash
snowl eval /absolute/path/to/my-eval
```

What happens:

1. terminal prints run bootstrap info and progress
2. once the run is actually initialized, Snowl prints a Web URL like `http://127.0.0.1:8765`
3. the eval stays in the foreground
4. stopping the eval also stops that auto-started monitor sidecar

Useful flags:

- filtering: `--task`, `--agent`, `--variant`
- limits: `--max-trials`, `--max-sandboxes`, `--max-builds`, `--max-model-calls`
- reliability: `--resume`, `--rerun-failed-only`
- monitor: `--no-web-monitor`
- legacy live CLI: `--cli-ui`

Manual monitor mode is still available:

```bash
snowl web monitor --project /absolute/path/to/my-eval --host 127.0.0.1 --port 8765
```

## Eval Folder Contract

Recommended eval folder layout:

```text
my-eval/
  task.py
  agent.py
  scorer.py
  model.yml        # recommended
  tool.py          # optional
  panels.yml       # optional
```

Autodiscovery contract:

- `task.py`: exports one or more `Task` objects or factories
- `agent.py`: exports one or more `Agent` / `AgentVariant` objects or factories
- `scorer.py`: exports scorer objects or factories
- `model.yml`: project-level provider + tested-model + optional judge config
- `tool.py`: optional tool definitions

Then run:

```bash
snowl eval /absolute/path/to/my-eval
```

## Multi-Model Authoring

Snowl's official multi-model path is project-level model matrix configuration.

Example `model.yml`:

```yaml
provider:
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
```

Semantics:

- `provider`: the example's single provider config
- `agent_matrix.models`: the tested agent models
- `judge.model`: optional scorer/judge model, separate from tested models

In `agent.py`, the recommended pattern is:

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

This same pattern is what now powers QA-style examples and container-heavy examples like TerminalBench and OSWorld.

## Execution Model

The current execution unit is:

- `Task x AgentVariant x Sample`

That is the real planning and runtime matrix Snowl executes today.

Conceptually, a full evaluation run has these stages:

1. project discovery
2. model matrix expansion into `AgentVariant`s
3. plan construction
4. runtime scheduling
5. trial execution
6. scoring and aggregation
7. artifact persistence
8. Web/CLI observability

Important current constraints:

- one active scorer per run
- experiment-level comparison is done across runs, not by one giant multi-benchmark scheduler
- concurrency is local-machine only today

## Artifacts And Observability

Each run writes under:

```text
<project>/.snowl/runs/<timestamp>/
```

Important artifacts:

- `run.log`: human-readable run log
- `events.jsonl`: structured live event stream
- `manifest.json`: run metadata and artifact contract
- `summary.json`: final summary counts
- `aggregate.json`: comparison/metric aggregation
- `profiling.json`: runtime and task monitor details
- `trials.jsonl`: trial-level results
- `metrics_wide.csv`: analysis-friendly metric export

The Web UI is built around these run artifacts plus the live event stream.

## Web UI

The built-in monitor is a Next.js app embedded in the package.

Current UX structure:

- `/`: run gallery landing
- `/runs/[runId]`: run workspace
- `/compare`: experiment/history comparison

Primary workflows:

- pick a run from the gallery
- inspect model-level and task-level status
- drill into runtime logs and pretask diagnostics
- compare experiments separately when needed

The UI is intentionally run-first, not experiment-first.

## Current Architecture Direction

Snowl is no longer just about “supporting more benchmarks.”
The hard next problem is making the runtime and orchestration layer industrial-grade.

That means the next serious work is around:

- concurrency scheduling
- build / sandbox / model-call backpressure
- container lifecycle robustness
- resumability under failure
- stronger artifact contracts
- clearer observability across long-running runs

If you are working on those problems, read [ARCHITECTURE.md](./ARCHITECTURE.md) first.

## Repo Map

Core framework:

- `snowl/core/`
- `snowl/eval.py`
- `snowl/runtime/`
- `snowl/envs/`
- `snowl/model/`
- `snowl/agents/`

Monitoring and UI:

- `snowl/cli.py`
- `snowl/web/`
- `webui/`
- `snowl/_webui/`

Benchmarks and examples:

- `snowl/benchmarks/`
- `examples/`
- `references/`

Validation and packaging:

- `tests/`
- `pyproject.toml`
- `setup.py`

## Recommended Read Order For Contributors

1. [AGENTS.md](./AGENTS.md)
2. [START_HERE.md](./START_HERE.md)
3. [ARCHITECTURE.md](./ARCHITECTURE.md)
4. [PLANS.md](./PLANS.md)
5. the subsystem code you are modifying

## Status Honesty

Snowl already has a strong base, but it is not yet an industrial scheduler.

What is strong already:

- shared eval contract
- official benchmark coverage
- multi-model authoring
- container-aware trial execution
- artifacts and monitoring

What is still the hardest unfinished work:

- industrial-grade runtime scheduling
- stronger fairness and backpressure across resources
- better fault isolation and recovery for container-heavy runs
- scaling beyond a single machine without breaking contracts

That is the work this repo is now moving toward.
