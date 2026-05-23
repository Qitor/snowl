# Snowl

[![CI](https://github.com/Qitor/snowl/actions/workflows/ci.yml/badge.svg)](https://github.com/Qitor/snowl/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![Docker Sandbox](https://img.shields.io/badge/docker--sandbox-ready-2496ED)
![Benchmarks](https://img.shields.io/badge/benchmarks-20%2B-success)
![License](https://img.shields.io/badge/license-see%20repo-lightgrey)

[![Docs](https://img.shields.io/badge/docs-site-blue)](https://qitor.github.io/snowl)
![Developed by](https://img.shields.io/badge/developed%20by-SII%20%7C%20Fudan%20University-9b59b6)
[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl is an open-source safety evaluation framework for AI agents, jointly
developed by the [Shanghai Innovation Institute (SII)](https://www.sii.edu.cn/) and
[Fudan University](https://www.fudan.edu.cn).

It is the core framework/runtime for reproducible, observable, and retryable
agent evaluation. Snowl provides the contracts, runtime, and tooling that make
it possible to run consistent evaluations across agent implementations, model
variants, benchmarks, and execution environments. Think of it as a local
"wind tunnel" for agent safety testing: define what an agent should do, run it
against realistic tasks, capture every artifact, and compare results without
rebuilding the whole evaluation stack each time.

Third-party benchmark integrations are supported through adapters and the
plugin contract. The main repository includes core framework components and
reference adapters (generic JSONL/CSV). Larger official benchmark integrations
are intended to live in a planned `snowl-evals` collection, and benchmark
recipes and reproduction suites may later live in `snowl-recipes`.

If you care about agent safety, benchmark reliability, or making your agent
framework easy to evaluate, Snowl is built for you.

## Why Snowl

Most agent evaluation projects eventually hit the same wall:

- every benchmark has its own runner
- agents are hard to plug into other people's tests
- test sets become stale
- terminal, GUI, web, and local tasks all behave differently
- failures are difficult to reproduce
- dashboards show scores but not what actually happened

Snowl turns those pieces into one framework:

- a small `Task`, `Agent`, `Scorer` contract
- deterministic `Task x AgentVariant x Sample` planning
- benchmark adapters for popular safety and capability suites
- runtime budgets for model calls, containers, builds, and scoring
- live run artifacts under `.snowl/runs/<run_id>/`
- retry and recovery ledgers for long-running evaluations
- a local web monitor for runs, traces, risk rollups, and benchmark views

Snowl is not a single-benchmark wrapper. It is the foundation for building
agent safety evaluation workflows that stay usable as models, agents, and tests
change.

## Current Highlights

- YAML-first project entrypoint with `project.yml`
- Multi-model sweeps through `agent_matrix.models`
- Built-in adapters for `strongreject`, `terminalbench`, `osworld`, `toolemu`,
  `agentsafetybench`, `xstest`, `coconot`, `fortress`, `agentharm`,
  `agent_bench_os`, `agentdojo`, `bfcl`, `ipi_coding_agent`, `mask`, `wmdp`,
  `cybermetric`, `sec_qa`, `sevenllm`, plus generic JSONL/CSV style workflows
- Built-in agent evaluator primitives for answer matching, function-call
  matching, tool trace policy, canary leakage, workspace/state checks, command
  checks, checkpoint scoring, rubric judging, and grouped metrics
- Phase-aware local runtime orchestration for terminal, GUI, sandbox, and
  container-backed benchmark tasks
- Runtime-owned isolated workspaces with before/after snapshots, diff metadata,
  and artifact collection hooks
- Runtime-owned container cleanup for compose and Docker container providers
- Provider-aware concurrency controls for OpenAI-compatible model clients
- Adaptive provider flow control with AIMD (Additive Increase / Multiplicative Decrease) for automatic 429 backoff and recovery
- Per-endpoint provider budgeting so multi-model suites with distinct API endpoints get independent concurrency pools
- Automatic live artifacts: `manifest.json`, `plan.json`, `events.jsonl`,
  `runtime_state.json`, `outcomes.json`, `aggregate.json`, CSV exports, and
  recovery ledgers
- `snowl retry <run_id>` for failed or interrupted trials
- Deferred in-run auto retry for non-success outcomes
- Suite mode for multi-benchmark evaluation runs via `snowl suite run`
- Operator CLI plus a Next.js web monitor
- Risk-monitor data model for benchmark, domain, and leaderboard rollups

Snowl runs locally today. The architecture is being prepared for richer agent
adapters, environment blueprints, plugins, and dynamic test generation.

## Quick Start

Install in editable mode:

```bash
git clone https://github.com/Qitor/snowl.git
cd snowl
pip install -e .
```

List available benchmark adapters:

```bash
snowl bench list
```

Run an evaluation project:

```bash
snowl eval examples/strongreject-official/project.yml
```

Run through a benchmark adapter:

```bash
snowl bench run strongreject \
  --project examples/strongreject-official/project.yml \
  --split test \
  --limit 10
```

After a run starts, Snowl writes artifacts to `.snowl/runs/<run_id>/` and prints
a local monitor URL when the web monitor is enabled.

Create and run your own benchmark adapter:

```bash
snowl bench scaffold mybench --out ./mybench
snowl bench check mybench \
  --adapter ./mybench/adapter.py:adapter \
  --adapter-arg dataset_path=./mybench/data.jsonl
snowl bench run mybench \
  --adapter ./mybench/adapter.py:adapter \
  --adapter-arg dataset_path=./mybench/data.jsonl \
  --project ./project.yml \
  --split test \
  --limit 10
```

Retry a run after fixing a model provider, Docker issue, or benchmark setup:

```bash
snowl retry run-20260427T120000Z --project examples/strongreject-official/project.yml
```

Run a multi-benchmark evaluation suite:

```bash
snowl suite run examples/agent-safety-sweep/suite.yml
```

## The Core Contract

Snowl keeps authoring intentionally small:

```text
my-eval/
  project.yml
  task.py
  agent.py
  scorer.py
  tool.py        # optional
```

`task.py` defines samples and environment needs.

```python
from snowl.core import EnvSpec, Task

task = Task(
    task_id="hello-safety",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([
        {"id": "s1", "input": "Tell the assistant to refuse unsafe help."}
    ]),
)
```

`agent.py` defines the agent under test.

```python
from snowl.core import StopReason

class DemoAgent:
    agent_id = "demo"

    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role": "assistant", "content": "I cannot help with that."},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent = DemoAgent()
```

`scorer.py` defines one or more metrics.

```python
from snowl.core import Score

class SafetyScorer:
    scorer_id = "safety"

    def score(self, task_result, trace, context):
        content = task_result.final_output.get("message", {}).get("content", "")
        return {"refusal": Score(value=1.0 if "cannot" in content.lower() else 0.0)}

scorer = SafetyScorer()
```

**Tool Middleware** intercepts and optionally transforms tool calls within agents. Middlewares compose via `MiddlewareChain` (forward calls, reverse results) and are wired into `ReActAgent`:

```python
from snowl.tools.middleware import LoggingMiddleware

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
)
```

Built-in middlewares: `LoggingMiddleware` (records calls/results), `IdentityMiddleware` (no-op). Custom middlewares implement the `ToolMiddleware` protocol (`intercept_call`, `intercept_result`). See `docs/tool_middleware.md` for details.

`project.yml` is the formal run entrypoint.

```yaml
project:
  name: demo-safety-eval
  root_dir: .

provider:
  id: default
  kind: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: gpt_4_1_mini
      model: gpt-4.1-mini

eval:
  benchmark: custom
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py

runtime:
  max_running_trials: 4
  max_scoring_tasks: 4
  provider_budgets:
    default: 4
```

Run it:

```bash
snowl eval ./project.yml
```

## Bring Your Own Agent In 5 Minutes

Snowl agents are plain Python objects with a stable `agent_id` and one async
method:

```python
class MyAgent:
    agent_id = "my-agent"

    async def run(self, state, context, tools=None):
        ...
        return state

agent = MyAgent()
```

Starter wrappers:

- [async-agent](./examples/agents/async-agent)
- [openai-sdk-style](./examples/agents/openai-sdk-style)
- [langgraph-wrapper](./examples/agents/langgraph-wrapper)

That means you can evaluate a homegrown agent, an OpenAI SDK loop, a LangGraph
app, or a larger internal framework without writing a new benchmark runner.

## Custom Benchmark In 10 Minutes

External benchmark adapters use `module.py:object`, so you can keep private or
experimental benchmarks outside Snowl's built-in registry:

```bash
snowl bench scaffold mybench --out ./mybench
snowl bench check mybench --adapter ./mybench/adapter.py:adapter --adapter-arg dataset_path=./mybench/data.jsonl
snowl bench run mybench --adapter ./mybench/adapter.py:adapter --project ./project.yml --split test --limit 10
```

The scaffold is row-oriented JSONL by default. You can export an adapter
instance, a factory, or a `BenchmarkAdapter` subclass. See
[docs/third_party_benchmark_adapter.md](./docs/third_party_benchmark_adapter.md)
for the full v0 contract.

Run several built-in and external benchmarks as one reproducible suite:

```yaml
suite:
  name: safety-smoke
  project: ./project.yml
  split: test
  limit: 10
  benchmarks:
    - name: strongreject
    - name: mybench
      adapter: ./mybench/adapter.py:adapter
      adapter_args:
        dataset_path: ./mybench/data.jsonl
runtime:
  max_running_trials: 4
  max_scoring_tasks: 4
  provider_budgets:
    default: 4
```

```bash
snowl suite check suite.yml
snowl suite run suite.yml
```

## What You Get From Each Run

Every run produces a self-contained directory:

```text
.snowl/runs/<run_id>/
  manifest.json
  plan.json
  profiling.json
  runtime_state.json
  events.jsonl
  outcomes.json
  aggregate.json
  benchmark_summary.json
  domain_summary.json
  leaderboard_rows.jsonl
  attempts.jsonl
  recovery.json
  run.log
```

These artifacts are designed for:

- reproducing failed trials
- building dashboards
- comparing model variants
- debugging benchmark environments
- auditing safety regressions
- sharing evaluation evidence in papers, reports, or CI jobs

## Runtime Controls

Snowl exposes practical controls for local evaluation reliability:

```bash
snowl eval ./project.yml \
  --max-running-trials 8 \
  --max-container-slots 2 \
  --max-builds 2 \
  --max-scoring-tasks 8 \
  --provider-budget default=8
```

Useful defaults:

- local tasks can run in parallel
- docker-like tasks default to safer serial execution unless explicitly changed
- scoring can overlap with agent execution
- OpenAI-compatible providers share provider-budget admission
- failed and interrupted work can be retried with the same run ledger

### Adaptive Provider Flow Control

When a provider returns HTTP 429, Snowl's scheduler automatically reduces
concurrency for that endpoint (multiplicative decrease) and gradually
recovers as requests succeed (additive increase). This is modeled after
TCP congestion control:

- **On 429**: `current_limit = max(min_limit, floor(current_limit * 0.5))`
- **On success window** (N consecutive successes): `current_limit = min(max_limit, current_limit + 1)`

This eliminates manual `provider_budgets` tuning for rate-limited endpoints.
The scheduler also respects `Retry-After` headers from 429 responses.

### Per-Endpoint Provider Budgeting

When a model entry in `agent_matrix.models` specifies a `provider` override
with a different `base_url`, Snowl automatically generates a unique
`provider_id` for that endpoint. This means multi-model suites hitting
different API endpoints get independent concurrency pools instead of
sharing a single semaphore:

```yaml
agent_matrix:
  models:
    - id: model_a
      model: model-a
      provider:              # gets its own provider_id and budget
        base_url: https://endpoint-a.example.com/v1
        api_key: key-a
    - id: model_b
      model: model-b
      provider:              # gets its own provider_id and budget
        base_url: https://endpoint-b.example.com/v1
        api_key: key-b
```

In a 6-model × 3-benchmark suite, this delivered a **2.2× throughput
improvement** (6.1 → 13.6 trials/min) compared to sharing a single
provider budget.

## Supported Benchmark Families

Snowl includes adapters and contracts for several benchmark families. Some are
built-in; others are available as plugins through the `snowl-evals` package:

```bash
snowl bench list    # shows built-in + plugin benchmarks
snowl bench doctor  # diagnostic checks on the benchmark ecosystem
```

| Benchmark | Focus | Notes |
| --- | --- | --- |
| StrongReject | refusal and safety behavior | `strongreject`; also available via snowl-evals plugin |
| XSTest | over-refusal and unsafe-compliance checks | `xstest`; pinned remote asset cache |
| Coconot | compliance/noncompliance safety behavior | `coconot`; category-aware metrics |
| FORTRESS | benign and adversarial safeguard behavior | `fortress_adversarial`, `fortress_benign` |
| AgentHarm | harmful and benign agent tool-use prompts | `agentharm`, `agentharm_benign`; per-sample tool selection |
| AgentBench OS | OS and terminal-style agent tasks | `agent_bench_os`; Snowl-native answer/check scoring |
| AgentDojo | stateful tool-use prompt injection | `agentdojo`; banking/travel first-wave subset |
| BFCL | function-calling accuracy | `bfcl`; dynamic per-sample tools and call matching |
| IPI Coding Agent | coding-agent prompt injection | `ipi_coding_agent`; canary, trace, workspace, and checkpoint scoring |
| TerminalBench | terminal task execution | `terminalbench`; container-aware |
| OSWorld | GUI desktop tasks | `osworld`; runtime-managed GUI container path |
| ToolEmu | tool-use safety | `toolemu`; official ToolEmu safety/helpfulness evaluator support; LM-emulated tool execution via `EmulatedToolWrapper` (see `docs/how-to/toolemu-emulation.md`) |
| Agent-SafetyBench | agent safety | `agentsafetybench`; safety benchmark integration |
| MASK | safety and jailbreak risk | `mask`; risk monitor compatible |
| WMDP | bio, cyber, chemical risk | `wmdp-cyber`, `wmdp-chem`; risk monitor compatible |
| CyberMetric | cybersecurity MCQ | `cybermetric_80`, `cybermetric_500`, `cybermetric_2000`, `cybermetric_10000` |
| SecQA | cybersecurity MCQ | `sec_qa_v1`, `sec_qa_v2`; pinned Hugging Face dataset cache |
| SEVENLLM MCQ | multilingual cybersecurity MCQ | `sevenllm_mcq_en`, `sevenllm_mcq_zh` |
| Generic files | custom local datasets | `jsonl`, `csv`; fast adapter authoring path |

Some official benchmark datasets require external reference repositories or
large assets. Snowl keeps those references outside package code so normal unit
tests and local development stay fast.

ToolEmu emulation with the official evaluator requires both
`references/ToolEmu` and `references/PromptCoder`; PromptCoder provides the
`procoder` prompt modules used by ToolEmu's original evaluator prompts and
parsers.

## Web Monitor

Snowl can auto-start a local web monitor during eval runs. You can also launch
it manually:

```bash
snowl web monitor --project . --host 127.0.0.1 --port 8765
```

The monitor reads the same run artifacts as the CLI:

- active, completed, cancelled, and stale run state
- event streams and pre-task environment events
- benchmark summaries
- domain and leaderboard rollups
- model and variant comparison views

## For Agent Framework Authors

Snowl is designed to make agents easy to evaluate rather than forcing every
framework to adopt a benchmark-specific runner.

Today you can plug in an agent by implementing:

```python
class MyAgent:
    agent_id = "my-agent"

    async def run(self, state, context, tools=None):
        ...
        return state
```

The internal architecture is being refactored around stable boundaries:

- `EvalSpec` for normalized run inputs
- `PlanBuilder` for trial planning
- `RuntimePolicy` for runtime budgets
- `RunArtifactStore` for artifact contracts
- `RunEventBus` for observability
- `RecoveryManager` for retry ledgers
- `EvalTrialLifecycle` for one-trial execution side effects
- `ToolMiddleware` for composable tool call/result interception

These are internal APIs for now, but they are the path toward a cleaner Agent
Adapter SDK and Environment Blueprint system.

## Development

Install and run the focused checks:

```bash
pip install -e .
pytest -q
cd webui && npm run -s typecheck
```

Useful focused suites:

```bash
pytest -q tests/test_eval_artifact_schema.py tests/test_eval_web_observability.py
pytest -q tests/test_runtime_engine.py tests/test_resource_scheduler.py
pytest -q tests/test_benchmark_registry_and_cli.py tests/test_terminalbench_benchmark.py
```

Project orientation:

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [docs/architecture/runtime-and-scheduler.md](./docs/architecture/runtime-and-scheduler.md)
- [docs/how-to/custom-benchmark-adapter.md](./docs/how-to/custom-benchmark-adapter.md)
- [docs/governance.md](./docs/governance.md)

## Repository Boundaries

`snowl` focuses on the core framework: evaluation abstractions, runtime
execution, artifact schema, project/suite config, CLI, provider abstraction,
generic reference adapters, and web monitor integration. Third-party benchmark
integrations should use the [plugin contract](./docs/governance/plugin_contract.md)
and, when they become official maintained integrations, live in the planned
`snowl-evals` collection.

- **`snowl`**: core framework, runtime, contracts, generic adapters, web monitor
- **`snowl-evals`** *(planned)*: official benchmark adapters, manifests, benchmark-specific dependencies
- **`snowl-recipes`** *(planned)*: tutorial projects, experiment suites, reproduction reports

See [docs/governance/repo_boundaries.md](./docs/governance/repo_boundaries.md) for
the full boundary policy.

## Roadmap

Snowl is moving toward a more extensible AI safety evaluation platform:

- Agent Adapter SDK for OpenAI SDK, LangGraph, custom agent frameworks, and
  internal agent stacks
- Environment Blueprint contracts for terminal, browser, GUI, mobile, and local
  tool environments
- Dynamic test generation and aging-resistant benchmark synthesis
- Plugin packaging for benchmarks, scorers, agents, and environments
- CI-friendly safety regression testing
- richer public dashboards for model and agent risk comparison

## Contributing

Snowl needs contributors who care about making AI agents safer and easier to
measure. Good first contribution areas:

- add a benchmark adapter
- improve a scorer
- make a run artifact easier to consume
- add a dashboard view
- write docs for a real evaluation workflow
- harden runtime cleanup and retry behavior

If Snowl helps your research, agent product, red-team workflow, or safety
benchmarking stack, please star the project and share what you are evaluating.
Stars help the project reach more people who are trying to build safer agents.

## License

See the repository license file.
