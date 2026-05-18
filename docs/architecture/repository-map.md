# Repository Map — Snowl

> Audited 2026-05-18. This document describes the **actual current state** of the
> repository. It does not project future features as if they already exist.

---

## 1. Architecture Overview

Snowl is a local, single-machine evaluation framework for AI agents with
safety-focused benchmark adapters. Its architecture has three primary layers:

1. **Core layer** (`snowl/core/`) — framework-independent contracts and validators
2. **Infrastructure layer** (`snowl/runtime/`, `snowl/agents/`, `snowl/model/`, `snowl/scorer/`, `snowl/tools/`, `snowl/envs/`) — execution engine, built-in agents, model clients, scorer implementations, tool middleware, environment runtimes
3. **Adapter layer** (`snowl/benchmarks/`) — 20+ benchmark adapters, each a sub-package

Orchestration glue sits at the top level: `cli.py`, `eval.py`, `dispatch.py`,
`eval_loop.py`, `bench.py`, `suite.py`, `project_config.py`, `planning.py`,
`artifacts.py`, `discovery.py`, `retry.py`.

Data flow is: `project.yml` → config loading → planning → `TrialRequest` →
agent execution → tool/middleware/runtime → scoring → `TaskResult`/`Score` →
artifact persistence → aggregation/reporting/web monitor.

---

## 2. Directory Map

```
snowl/
├── __init__.py              # Public API facade (re-exports from core, agents, model, scorer, envs, runtime)
├── __main__.py              # python -m snowl entry point
├── artifacts.py             # Run artifact persistence (manifest, plan, events, outcomes, aggregates)
├── bench.py                 # `snowl bench` orchestration
├── cli.py                   # CLI entry point (~2100 lines, single file)
├── discovery.py             # Project code loading, @task/@agent/@scorer decorator resolution
├── dispatch.py              # Main dispatch loop, scheduling, auto-retry, artifact management (~1327 lines)
├── errors.py                # SnowlValidationError (stdlib only)
├── eval.py                  # `snowl eval` entry, run bootstrap, Web monitor sidecar lifecycle
├── eval_loop.py             # Single-trial lifecycle: prepare → execute → score → finalize
├── eval_spec.py             # EvalSpec: normalized run inputs
├── examples_lint.py         # Lint examples for secret hygiene
├── planning.py              # PlanBuilder: task × agent × sample → PlanTrial expansion
├── project_config.py        # project.yml loader (depends on yaml, snowl.model.openai_compatible)
├── rescore.py               # Re-score a completed run
├── retry.py                 # `snowl retry` orchestration
├── suite.py                 # `snowl suite` multi-benchmark orchestration
│
├── core/                    # ── CORE LAYER (zero third-party deps, zero adapter imports) ──
│   ├── __init__.py          # Re-exports all core contracts
│   ├── agent.py             # Agent protocol, AgentState, AgentContext, Action, Observation, StopReason
│   ├── agent_variant.py     # AgentVariant, AgentVariantAdapter, bind/make helpers
│   ├── declarations.py      # @task, @agent, @scorer decorator stamps (declare())
│   ├── env.py               # EnvSpec, SandboxSpec, FileOps, ProcessOps, WebOps
│   ├── scorer.py            # Scorer/AsyncScorer protocols, Score, ScoreContext, @scorer
│   ├── task.py              # Task, TaskProvider protocol, @task
│   ├── task_result.py       # TaskResult, TaskStatus, Timing, Usage, ErrorInfo, ArtifactRef
│   └── tool.py              # ToolSpec, ToolRegistry, build_tool_spec, @tool
│
├── agents/                  # ── BUILT-IN AGENT IMPLEMENTATIONS ──
│   ├── __init__.py          # Re-exports ChatAgent, ReActAgent
│   ├── chat_agent.py        # Single-call baseline (uses ChatModelClient protocol)
│   ├── model_variants.py    # AgentVariant expansion from project model_matrix
│   └── react_agent.py       # Plan/Act/Observe loop with tool-schema injection (uses ChatModelClient)
│
├── aggregator/              # ── RUN AGGREGATION ──
│   ├── __init__.py
│   ├── metrics.py           # Metric computation helpers
│   ├── schema.py            # Result schema URI and version
│   └── summary.py           # Aggregate summaries, benchmark/domain/leaderboard rollups
│
├── benchmarks/              # ── BENCHMARK ADAPTERS (20+) ──
│   ├── __init__.py
│   ├── assets.py            # Asset resolution (remote cache, pinned downloads)
│   ├── base.py              # BenchmarkAdapter protocol, BenchmarkConcurrencyProfile, BenchmarkInfo
│   ├── base_adapter.py      # BaseBenchmarkAdapter template (iter_rows → row_to_sample)
│   ├── conformance.py       # Adapter conformance validation
│   ├── csv_adapter.py       # Generic CSV adapter
│   ├── example_task.py      # Sample task generation helpers
│   ├── external.py          # External adapter loading (module:object)
│   ├── jsonl_adapter.py     # Generic JSONL adapter
│   ├── registry.py          # Benchmark registry (register_builtin_benchmarks)
│   ├── utils/               # Shared benchmark utilities
│   │   ├── filtering.py     # Task/sample filtering
│   │   ├── io.py            # I/O helpers
│   │   ├── paths.py         # Path resolution
│   │   ├── split.py         # Train/test split logic
│   │   └── task_builder.py  # Task construction helpers
│   ├── agent_bench_os/      # OS/terminal tasks
│   ├── agentdojo/           # Stateful tool-use prompt injection
│   ├── agentharm/           # Harmful/benign agent prompts
│   ├── agentsafetybench/    # Agent safety
│   ├── bfcl/                # Function-calling accuracy
│   ├── coconot/             # Compliance/noncompliance
│   ├── cybermetric/         # Cybersecurity MCQ
│   ├── fortress/            # Safeguard behavior
│   ├── ipi_coding_agent/    # Coding-agent prompt injection
│   ├── mask/                # Safety/jailbreak risk
│   ├── osworld/             # GUI desktop tasks
│   ├── sec_qa/              # Cybersecurity MCQ
│   ├── sevenllm/            # Multilingual cybersecurity MCQ
│   ├── strongreject/        # Refusal/safety behavior
│   ├── terminalbench/       # Terminal task execution
│   ├── toolemu/             # Tool-use safety (ToolEmu evaluator support)
│   ├── wmdp/                # Bio/cyber/chemical risk
│   └── xstest/              # Over-refusal checks
│
├── envs/                    # ── ENVIRONMENT RUNTIMES ──
│   ├── __init__.py          # Re-exports LocalEnv, LocalSandboxRuntime, GuiEnv, TerminalEnv
│   ├── gui_env.py           # GUI desktop environment (VNC/screenshot)
│   ├── local_env.py         # Local filesystem environment
│   ├── sandbox_runtime.py   # Sandbox runtime abstraction
│   ├── terminal_env.py      # Terminal environment (docker compose)
│   └── substrate/           # Low-level execution substrate
│       ├── command_runner.py    # Shell command execution
│       ├── container_backend.py # Docker CLI wrapper
│       ├── gui_action_translator.py # GUI action → container command
│       └── http_runner.py       # HTTP-based execution
│
├── export/                  # ── EXPORT / TRACE ──
│   ├── __init__.py
│   └── openai_trace.py      # OpenAI trace format export
│
├── model/                   # ── MODEL PROVIDER ADAPTERS ──
│   ├── __init__.py          # Re-exports OpenAICompatibleChatClient, configs
│   ├── base.py              # ChatModelClient protocol (generate, generate_stream)
│   ├── openai_compatible.py # OpenAI-compatible HTTP client (httpx-based)
│   └── project_matrix.py    # Model matrix resolution from project config
│
├── observability/           # ── EVENT / OBSERVABILITY ──
│   ├── __init__.py
│   └── events.py            # RunEventBus, event emission, PlanTrial event types
│
├── report/                  # ── REPORTING ──
│   ├── __init__.py
│   ├── compare.py           # Run comparison
│   └── html.py              # HTML report generation
│
├── runtime/                 # ── RUNTIME ENGINE ──
│   ├── __init__.py          # Re-exports TrialRequest, TrialOutcome, TrialLimits, execute_trial
│   ├── container_contract.py    # RuntimeContainerSpec, workspace/env resource specs
│   ├── container_lifecycle.py   # Container lifecycle manager (build, start, stop)
│   ├── container_providers.py   # ContainerProvider registry + concrete providers
│   ├── container_runtime.py     # Container runtime orchestration
│   ├── engine.py                # Trial execution engine (prepare/execute/score/finalize)
│   ├── policy.py                # RuntimeBudgetResolution, auto_container_slots heuristics
│   ├── recovery.py              # RecoveryManager (attempts.jsonl, recovery.json)
│   ├── resource_scheduler.py    # ResourceScheduler (semaphores, AIMD flow control)
│   ├── results.py               # TrialOutcome, PartialTrialResult, FinalTrialOutcome
│   └── workspace.py             # RuntimeWorkspace (before/after snapshots, artifact collection)
│
├── scorer/                  # ── SCORER IMPLEMENTATIONS ──
│   ├── __init__.py          # Re-exports includes, match, pattern, model_as_judge_json, etc.
│   ├── agent.py             # Agent-specific scorers
│   ├── base.py              # Scorer base helpers
│   ├── choice.py            # Multiple-choice scoring
│   ├── composition.py       # Scorer composition (all_of, any_of)
│   ├── grade_judge.py       # Grade/rubric judging
│   ├── model_judge.py       # LLM-as-judge scoring
│   ├── test_results.py      # Test-result-based scoring
│   ├── text.py              # Text matching scorers (includes, pattern, match)
│   └── trace.py             # Tool trace policy scoring
│
├── tools/                   # ── TOOL MIDDLEWARE / EXECUTION ──
│   ├── __init__.py
│   ├── emulated_tool.py     # EmulatedToolWrapper (LM-simulated tool execution)
│   ├── gui.py               # GUI tool actions
│   ├── injection.py         # Tool injection middleware
│   ├── middleware.py         # ToolMiddleware protocol, MiddlewareChain, LoggingMiddleware
│   ├── stateful_executor.py # Stateful tool execution (includes AgentDojo tool implementations)
│   └── terminal.py          # Terminal tool actions
│
├── ui/                      # ── CONSOLE / WEB UI ──
│   ├── __init__.py
│   ├── console.py           # Rich-based console renderer
│   ├── contracts.py         # UI event contracts, TaskMonitor protocol
│   ├── controls.py          # Interactive controls
│   ├── input.py             # User input handling
│   └── panels.py            # Dashboard panels
│
├── utils/                   # ── SHARED UTILITIES ──
│   ├── __init__.py
│   └── env.py               # Environment variable helpers
│
└── web/                     # ── WEB MONITOR BACKEND ──
    ├── __init__.py
    ├── monitor.py           # SQLite-backed run index + event stream consumer
    └── runtime.py           # Web runtime (Next.js sidecar management)
```

### Supporting directories

```
tests/                       # Test suite (538 passing, 1 failing, 5 skipped as of audit)
docs/                        # Documentation site
webui/                       # Next.js web monitor (source of truth for UI)
  src/                       # React/Next.js source
snowl/_webui/                # Packaged mirror of webui build output
references/                  # External reference code (ToolEmu, AgentDojo, PromptCoder, BFCL, etc.)
  ToolEmu/                   # ToolEmu reference implementation
  agentdojo/                 # AgentDojo reference implementation
  PromptCoder/               # PromptCoder prompt modules
  bfcl/                      # BFCL reference
.github/workflows/           # CI (ci.yml) and PyPI publish (pypi-publish.yml)
```

---

## 3. User-Facing Surfaces

### 3.1 CLI

The `snowl` CLI provides these subcommands:

| Command | Description |
|---------|-------------|
| `snowl eval <project.yml>` | Run an evaluation project |
| `snowl bench list` | List available benchmark adapters |
| `snowl bench run <benchmark>` | Run a specific benchmark |
| `snowl bench scaffold <name>` | Scaffold a new benchmark adapter |
| `snowl bench check <benchmark>` | Validate a benchmark adapter |
| `snowl suite run <suite.yml>` | Run a multi-benchmark suite |
| `snowl suite check <suite.yml>` | Validate a suite config |
| `snowl retry <run_id>` | Retry failed/interrupted trials |
| `snowl rescore <run_id>` | Re-score a completed run |
| `snowl web monitor` | Start the web monitor |

### 3.2 project.yml

The YAML-first project entrypoint. Key sections:
- `project`: name, root_dir
- `provider`: id, kind (openai_compatible), base_url, api_key, timeout, max_retries
- `agent_matrix.models`: list of model entries with id, model, optional provider override
- `eval`: benchmark name, code paths, split, limit
- `runtime`: concurrency controls
- `benchmarks.<name>`: benchmark-specific config

### 3.3 Benchmark adapter mode

`snowl bench run <benchmark>` uses the built-in registry to load a benchmark
adapter, which provides its own task samples, default agent, and default scorer.
External adapters use `--adapter module.py:object`.

### 3.4 Suite mode

`snowl suite run suite.yml` runs multiple benchmarks in one reproducible
evaluation, sharing provider config and runtime settings.

### 3.5 Run artifact directory

Every run produces a self-contained directory at `.snowl/runs/<run_id>/`:

| Artifact | Purpose |
|----------|---------|
| `manifest.json` | Run metadata, provider, models |
| `plan.json` | Planned trials (task × agent × sample) |
| `events.jsonl` | Live event stream (appended during execution) |
| `runtime_state.json` | Runtime state snapshots |
| `outcomes.json` | Per-trial outcomes |
| `aggregate.json` | Aggregated metrics |
| `profiling.json` | Timing and resource profiles |
| `trials.jsonl` | Trial records |
| `metrics_wide.csv` | Wide-format metrics export |
| `benchmark_summary.json` | Per-benchmark rollup |
| `domain_summary.json` | Per-domain rollup |
| `leaderboard_rows.jsonl` | Leaderboard data |
| `attempts.jsonl` | Retry attempt history |
| `recovery.json` | Recovery ledger |
| `run.log` | Captured log output |

### 3.6 Web monitor

Next.js full-stack monitor at `/`. Sub-pages:
- `/runs/[runId]` — single-run workspace
- `/compare` — history comparison view

Reads from `.snowl/runs/`, consumes live `events.jsonl`, indexes in SQLite.

---

## 4. Extension Points

### 4.1 Custom agent

Implement `Agent` protocol from `snowl.core`:

```python
class MyAgent:
    agent_id = "my-agent"
    async def run(self, state, context, tools=None):
        ...
        return state
```

### 4.2 Benchmark adapter

Subclass `BaseBenchmarkAdapter` in `snowl/benchmarks/`, implement
`_iter_rows`, `_row_split`, `_row_to_sample`. Or use the
external adapter path: `snowl bench run --adapter module.py:object`.

### 4.3 Scorer

Implement `Scorer` or `AsyncScorer` protocol from `snowl.core`:

```python
class MyScorer:
    scorer_id = "my-scorer"
    def score(self, task_result, trace, context):
        return {"metric": Score(value=1.0)}
```

### 4.4 Model provider

Implement `ChatModelClient` protocol from `snowl.model.base`:

```python
class MyModelClient:
    async def generate(self, messages, tools=None, **kwargs):
        ...
```

### 4.5 Tool middleware

Implement `ToolMiddleware` protocol from `snowl.tools.middleware`:

```python
class MyMiddleware:
    async def intercept_call(self, call, context):
        return call
    async def intercept_result(self, result, context):
        return result
```

### 4.6 Environment/container runtime

Add a `ContainerProvider` implementation in the runtime layer and register it
in `default_container_provider_registry()`.

### 4.7 Report/export/dashboard

Current exports: OpenAI trace format, HTML report, CSV metrics. The web monitor
is the primary dashboard. Adding new exporters or dashboard views is possible
through the artifact directory contract.

---

## 5. Data Flow

```
project.yml
  → project_config.py (YAML → ProjectConfig)
  → discovery.py (load task.py, agent.py, scorer.py, tool.py)
  → agents/model_variants.py (expand model entries → AgentVariants)
  → planning.py (Task × AgentVariant × Sample → PlanTrial list)
  → dispatch.py (schedule trials, manage concurrency)
    → eval_loop.py (per-trial lifecycle)
      → runtime/engine.py: prepare_trial_phase (build TrialRequest, AgentState)
      → runtime/engine.py: execute_agent_phase (Agent.run → PartialTrialResult)
        → tools/middleware.py (MiddlewareChain wraps tool calls)
        → envs/ (container lifecycle for docker-like tasks)
      → runtime/engine.py: score_trial_phase (Scorer.score → Score)
      → runtime/engine.py: finalize_trial_phase (assemble TaskResult)
    → artifacts.py (persist manifest, plan, events, outcomes, aggregates)
    → aggregator/ (benchmark_summary, domain_summary, leaderboard)
  → CLI output + Web monitor
```

---

## 6. API Stability Classification

### Stable / Public

These are the intentional public APIs re-exported from `snowl` and `snowl.core`:

| API | Location | Notes |
|-----|----------|-------|
| `Task`, `TaskProvider`, `@task` | `snowl.core.task` | Core contract |
| `Agent`, `AgentState`, `AgentContext`, `StopReason` | `snowl.core.agent` | Core protocol |
| `AgentVariant`, `AgentVariantAdapter` | `snowl.core.agent_variant` | Variant metadata |
| `Scorer`, `AsyncScorer`, `Score`, `ScoreContext` | `snowl.core.scorer` | Core protocol |
| `TaskResult`, `TaskStatus`, `Timing`, `Usage` | `snowl.core.task_result` | Core data model |
| `ToolSpec`, `ToolRegistry`, `build_tool_spec` | `snowl.core.tool` | Core tool contract |
| `EnvSpec`, `SandboxSpec` | `snowl.core.env` | Core environment spec |
| `ChatAgent`, `ReActAgent` | `snowl.agents` | Built-in agents |
| `ChatModelClient` | `snowl.model.base` | Model client protocol |
| `OpenAICompatibleChatClient` | `snowl.model` | Concrete model client |
| `includes`, `match`, `pattern`, `model_as_judge_json` | `snowl.scorer` | Built-in scorers |
| `TrialRequest`, `TrialOutcome`, `TrialLimits` | `snowl.runtime` | Runtime types |
| `execute_trial` | `snowl.runtime` | Trial execution entry |
| `LocalEnv`, `LocalSandboxRuntime` | `snowl.envs` | Environment runtimes |
| `SnowlValidationError` | `snowl.errors` | Error type |

### Internal / Experimental

These are used within the framework but not intended as stable public APIs:

| API | Location | Notes |
|-----|----------|-------|
| `dispatch.py` (entire module) | `snowl.dispatch` | Internal orchestrator |
| `eval_loop.py` | `snowl.eval_loop` | Internal lifecycle |
| `EvalSpec` | `snowl.eval_spec` | May stabilize |
| `PlanBuilder`, `PlanTrial` | `snowl.planning` | May stabilize |
| `RunArtifactStore` | `snowl.artifacts` | May stabilize |
| `RunEventBus` | `snowl.observability.events` | May stabilize |
| `RuntimePolicy` | `snowl.runtime.policy` | Internal |
| `ResourceScheduler` | `snowl.runtime.resource_scheduler` | Internal |
| `RecoveryManager` | `snowl.runtime.recovery` | Internal |
| `ToolMiddleware`, `MiddlewareChain` | `snowl.tools.middleware` | May stabilize |
| `ContainerProvider` | `snowl.runtime.container_providers` | Experimental |
| `BaseBenchmarkAdapter` | `snowl.benchmarks.base_adapter` | May stabilize for external adapters |
| `BenchmarkRegistry` | `snowl.benchmarks.registry` | Internal |
