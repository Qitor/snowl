# Snowl Governance: Architecture Audit, Target Design & Refactoring Plan

> Generated 2026-05-14. This document is the single source of truth for Snowl's
> architecture governance, core/adapter boundary, and open-source readiness.

---

## Part 1: Architecture Audit

### 1.1 Current Repository Structure

```
snowl/
├── core/                  # Contracts: Task, Agent, Scorer, ToolSpec, EnvSpec, TaskResult
│   ├── agent.py           #   Agent protocol, AgentState, AgentContext
│   ├── agent_variant.py   #   AgentVariant metadata
│   ├── declarations.py    #   @task/@agent/@scorer decorator stamps
│   ├── env.py             #   EnvSpec, SandboxSpec
│   ├── scorer.py          #   Scorer/AsyncScorer protocols, Score, ScoreContext
│   ├── task.py            #   Task, TaskProvider protocol
│   ├── task_result.py     #   TaskResult, TaskStatus, Timing, Usage
│   └── tool.py            #   ToolSpec, ToolRegistry, build_tool_spec
├── agents/                # Agent implementations (ReActAgent, ChatAgent)
├── benchmarks/            # 20+ benchmark adapters (each a sub-package)
├── cli.py                 # CLI entry point (~71KB, single file)
├── envs/                  # Environment implementations (Local, Sandbox, GUI, Terminal)
├── errors.py              # Shared SnowlValidationError
├── eval/                  # Eval run orchestration
├── export/                # OpenAI trace export
├── model/                 # ChatModelClient protocol + OpenAICompatibleChatClient
├── project_config.py      # project.yml loader
├── runtime/               # Trial execution engine, scheduler, policy, containers
├── scorer/                # 40+ scorer implementations
├── tools/                 # ToolMiddleware, StatefulToolExecutor, EmulatedToolWrapper
└── ui/                    # Console/Web rendering
```

### 1.2 Inferred Architecture

```
                     ┌─────────────┐
                     │   CLI (71K) │
                     └──────┬──────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                  │
    ┌─────┴──────┐   ┌─────┴──────┐   ┌──────┴──────┐
    │   Runtime   │   │    Eval    │   │     UI      │
    │  Engine     │   │ Bootstrap  │   │  Renderer   │
    └─────┬──────┘   └─────┬──────┘   └─────────────┘
          │                │
    ┌─────┴────────────────┴──────────────────────┐
    │          Integration Layer                   │
    │  ┌──────────┐ ┌────────┐ ┌───────────────┐  │
    │  │  Agents   │ │ Model  │ │   Scorers     │  │
    │  │ ReAct/Chat│ │ Client │ │ 40+ variants  │  │
    │  └────┬─────┘ └───┬────┘ └───────┬───────┘  │
    │       │           │              │           │
    │  ┌────┴───────────┴──────────────┴───────┐  │
    │  │            Core Layer                  │  │
    │  │  Task · Agent · Scorer · ToolSpec     │  │
    │  │  EnvSpec · TaskResult · Score          │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ┌──────────────────────────────────────┐   │
    │  │       Benchmark Adapters (20+)       │   │
    │  └──────────────────────────────────────┘   │
    └─────────────────────────────────────────────┘
```

### 1.3 Core Layer Assessment

**Verdict: Clean.** The core layer (`snowl/core/`) has **zero imports** from any non-core `snowl` package and **zero third-party dependencies**. It depends only on Python stdlib and `snowl.errors.SnowlValidationError`.

Internal dependency graph (clean DAG, no cycles):
```
declarations.py  ← (no snowl imports)
    ↑
agent.py ────────→ declarations, errors
    ↑
agent_variant.py → agent, errors

env.py ──────────→ errors

task.py ─────────→ declarations, env, errors

task_result.py ──→ errors
    ↑
scorer.py ───────→ declarations, task_result, errors

tool.py ─────────→ errors
```

**Two soft coupling concerns** (not import violations, but design opinions):
1. `SandboxSpec` fields (`image`, `dockerfile`, `build_context`) embed Docker/container assumptions
2. `ToolSpec.to_openai_tool()` embeds OpenAI function-calling schema format

### 1.4 Boundary Violations

| Severity | Location | Violation |
|----------|----------|-----------|
| **HIGH** | `snowl/agents/react_agent.py:24` | `ReActAgent` requires `OpenAICompatibleChatClient` instead of `ChatModelClient` protocol |
| **HIGH** | `snowl/agents/chat_agent.py:22` | `ChatAgent` requires `OpenAICompatibleChatClient` instead of `ChatModelClient` protocol |
| **HIGH** | `snowl/tools/emulated_tool.py:28` | `EmulatedToolWrapper` requires `OpenAICompatibleChatClient` instead of `ChatModelClient` protocol |
| **MEDIUM** | ~~`snowl/runtime/policy.py:9`~~ | ~~Runtime imports `BenchmarkConcurrencyProfile` from benchmarks (reversed dependency direction)~~ **RESOLVED**: `BenchmarkConcurrencyProfile` now only imported under `TYPE_CHECKING`; `resolve()` accepts it as a parameter |
| **MEDIUM** | ~~`snowl/runtime/policy.py:90-97`~~ | ~~Runtime queries benchmark registry at runtime (deferred circular import)~~ **RESOLVED**: `resolve()` receives `concurrency_profile` from caller (dispatch.py); fallback helper `_get_benchmark_profile_from_registry()` is optional |
| **MEDIUM** | ~~`snowl/runtime/container_providers.py:25`~~ | ~~Runtime imports `OSWorldContainerLauncher` from a specific benchmark~~ **RESOLVED**: Provider entry_points now use `register_providers(registry)` convention; no benchmark imports in runtime |
| **MEDIUM** | `snowl/runtime/engine.py:961` | ~~Engine checks `output.get("osworld_score")`~~ **RESOLVED**: replaced with generic `_get_extra_payload_keys()` that reads from benchmark registry |
| **LOW** | `snowl/tools/stateful_executor.py:53-408` | ~~AgentDojo-specific tool implementations in shared `snowl/tools/` package~~ **RESOLVED**: moved to `snowl/benchmarks/agentdojo/tools.py` |
| **LOW** | `snowl/benchmarks/base_adapter.py:46-48` | `benchmark_info()` does deferred import of registry (semantic coupling) |

### 1.5 Duplicate Abstractions

| Duplication | Locations | Fix |
|-------------|-----------|-----|
| `_run_coro_sync()` | ~~`scorer/model_judge.py:30-52`, `scorer/grade_judge.py:20-40`~~ **RESOLVED**: extracted to `scorer/_sync_bridge.py` |
| Template rendering | ~~`scorer/model_judge.py` (`_render_template`), `scorer/grade_judge.py` (`render_prompt_template`)~~ **RESOLVED**: unified to `scorer/_prompt.py:render_judge_prompt()` |
| `_tool_schemas()` | ~~`benchmarks/bfcl/adapter.py`, `benchmarks/agentdojo/adapter.py`~~ **RESOLVED**: extracted to `benchmarks/utils.py:normalize_tool_schemas()` |

### 1.6 Overly Large Files

| File | Lines | Concern |
|------|-------|---------|
| `snowl/cli.py` | ~2,100 | Single monolithic CLI; could decompose into subcommand modules |
| `snowl/runtime/engine.py` | ~1,355 | Handles prepare, execute, score, finalize, workspace, containers, middleware all in one file |
| `snowl/tools/emulated_tool.py` | ~700 | Contains 6+ classes and all ToolEmu prompt templates |

### 1.7 Security Risks

| Risk | Location | Detail |
|------|----------|--------|
| **CRITICAL** | `examples/strongreject-official/project.yml:9` | Contains API key `sk-irodedqyvgqjdilarnwmrixfwigoxvaenmcfnjmfvbaxrkxm` |
| **CRITICAL** | `examples/wmdp-cyber-eval/project.yml:9` | Same leaked API key |
| **HIGH** | ~~`snowl/runtime/engine.py:779-783`~~ | ~~`OpenAICompatibleChatClient` instantiated with wrong constructor signature — latent runtime bug~~ **RESOLVED**: Fixed to use `OpenAICompatibleConfig` dataclass |

### 1.8 Test Organization

**Core contract tests** (clean, independent):
- `test_task_contracts.py`, `test_scorer_contracts.py`, `test_agent_contracts.py`, `test_tool_spec.py`, `test_task_result.py`, `test_async_scorer_protocol.py`, `test_tool_middleware.py`

**Adapter smoke tests** (good coverage):
- Per-benchmark test files following consistent pattern: registry presence → conformance → determinism → scorer → example importability

**Gaps**:
- No dedicated test for `__all__` public API stability
- `test_runtime_engine.py` couples `execute_trial` to `ChatAgent` + `OpenAICompatibleChatClient` rather than pure stubs
- No architecture boundary test (e.g., import check that core never imports adapters)

### 1.9 Missing Governance Files

| File | Status |
|------|--------|
| `CONTRIBUTING.md` | Missing |
| `CHANGELOG.md` | Missing |
| `CLAUDE.md` | Missing |
| `docs/testing.md` | Missing |
| `docs/development.md` | Missing |
| `docs/compatibility.md` | Missing |
| `docs/release_process.md` | Missing |
| `docs/public_api.md` | Missing |
| `docs/extension_points.md` | Missing |
| `.github/pull_request_template.md` | Missing |

### 1.10 README Issues

- References `START_HERE.md` and `PLANS.md` — both deleted and gitignored
- References `docs/project_map.md` and `docs/current_state.md` — both deleted

---

## Part 2: Target Architecture

### 2.1 Core Layer Responsibilities

The core layer (`snowl/core/`) owns:
- **Data models**: `TaskResult`, `Score`, `ScoreContext`, `EnvSpec`, `AgentState`
- **Protocols**: `Agent`, `Scorer`, `AsyncScorer`, `TaskProvider`, `ChatModelClient` (when moved here)
- **Declarations**: `@task`, `@agent`, `@scorer`, `@tool` decorators
- **Validation**: Contract validators (`validate_task`, `validate_agent`, etc.)
- **Tool primitives**: `ToolSpec`, `ToolRegistry`, `build_tool_spec`

Core must remain:
- **Framework-independent**: no httpx, openai, docker, rich, click
- **Provider-agnostic**: no provider names, URLs, API keys
- **Benchmark-agnostic**: no benchmark-specific field names or scoring logic
- **Zero third-party dependencies**: only Python stdlib + `snowl.errors`

### 2.2 Adapter Layer Responsibilities

Adapters implement concrete behavior around core contracts:
- **Benchmark adapters** (`snowl/benchmarks/`): Load datasets, map rows to core `SampleData`, provide benchmark-specific agents and scorers
- **Model adapters** (`snowl/model/`): Implement `ChatModelClient` protocol for specific providers
- **Agent implementations** (`snowl/agents/`): Implement core `Agent` protocol using model clients
- **Scorer implementations** (`snowl/scorer/`): Implement core `Scorer` protocol
- **Environment implementations** (`snowl/envs/`): Implement `EnvSpec`-defined capabilities

### 2.3 Dependency Direction Rules

**Allowed** (arrows mean "depends on"):
```
agents ──→ core
agents ──→ model (for ChatModelClient protocol)
benchmarks ──→ core
benchmarks ──→ agents (for ReActAgent)
benchmarks ──→ model (for client construction)
scorer ──→ core
scorer ──→ model (for judge scorers only)
tools ──→ core
tools ──→ model (for EmulatedToolWrapper only)
runtime ──→ core
runtime ──→ agents
runtime ──→ model
cli ──→ everything (top-level orchestrator)
```

**Forbidden**:
```
core ──→ agents         # Core must not know about ReActAgent
core ──→ benchmarks     # Core must not know about specific benchmarks
core ──→ model          # Core must not know about provider implementations
core ──→ runtime        # Core must not know about execution engine
core ──→ scorer (impls) # Core must not know about concrete scorers
core ──→ tools (impls)  # Core must not know about middleware implementations
core ──→ any 3rd party  # Core must not import httpx, openai, docker, etc.
runtime ──→ benchmarks  # Runtime must not import specific benchmark code
```

### 2.4 Adding a New Benchmark Adapter

1. Create `snowl/benchmarks/<name>/` with `adapter.py` subclassing `BaseBenchmarkAdapter`
2. Implement template methods: `_iter_rows`, `_row_split`, `_row_to_sample`
3. Optionally add `agent.py`, `scorer.py`, `executor.py` for benchmark-specific logic
4. Register in `snowl/benchmarks/registry.py` via `register_builtin_benchmarks()`
5. Add tests in `tests/test_<name>_benchmark.py`
6. Add example project in `examples/<name>/`

### 2.5 Adding a New Model Provider

1. Create a class implementing the `ChatModelClient` protocol from `snowl/model/base.py`
2. Place in `snowl/model/` or a separate package
3. Ensure `ReActAgent` and `ChatAgent` accept it via the protocol (fix current concrete coupling first)

### 2.6 Testing Core Logic Independently

Core tests must:
- Use only `snowl.core` imports and stdlib
- Never import from `snowl.agents`, `snowl.model`, `snowl.scorer`, `snowl.benchmarks`, `snowl.runtime`
- Use pure dataclass/protocol instances, no mocking of adapters
- Validate contracts, not implementation details

### 2.7 Testing Adapters with Minimal Fixtures

Adapter tests should:
- Use `tmp_path` for test datasets (not real reference corpora)
- Mock `ChatModelClient.generate()` with `httpx.MockTransport` for model-dependent tests
- Verify: registry presence, conformance, sample determinism, scorer logic, example importability
- Never require real API keys or network access

### 2.8 What Must Never Be Placed in Core

- Provider-specific constructors or factory functions
- Benchmark-specific field names or score keys
- HTTP clients, API keys, endpoint URLs
- Container/Docker assumptions beyond `SandboxSpec` data model
- CLI argument parsing
- File I/O beyond stdlib `json`/`pathlib`
- Template rendering engines (Jinja2)
- Console rendering (Rich)
- Configuration loading (YAML, .env)

---

## Part 3: Refactoring Plan

### P0 — Must Fix Before Open-Source Release

#### P0.1: Remove leaked API keys from examples

- **Problem**: `examples/strongreject-official/project.yml` and `examples/wmdp-cyber-eval/project.yml` contain a SiliconFlow API key in plaintext
- **Files**: `examples/strongreject-official/project.yml`, `examples/wmdp-cyber-eval/project.yml`
- **Why it matters**: Security risk; key exposure in public repo
- **Violates core/adapters?**: No, but violates basic security hygiene
- **Risk level**: Low (simple text replacement)
- **Strategy**: Replace `sk-irodedqyvgqjdilarnwmrixfwigoxvaenmcfnjmfvbaxrkxm` with `${OPENAI_API_KEY}` placeholder
- **Validation**: `grep -r 'sk-' examples/` returns zero hits
- **Public behavior change**: No

#### P0.2: Fix README broken references

- **Problem**: README references `START_HERE.md`, `PLANS.md`, `docs/project_map.md`, `docs/current_state.md` — all deleted
- **Files**: `README.md`
- **Why it matters**: Broken links in public-facing README
- **Violates core/adapters?**: No
- **Risk level**: Low
- **Strategy**: Remove or replace references with existing docs paths
- **Validation**: `grep -E 'START_HERE|PLANS\.md|project_map|current_state' README.md` returns zero hits
- **Public behavior change**: No

#### P0.3: Add CONTRIBUTING.md and CLAUDE.md

- **Problem**: No contribution guidelines or AI-agent governance file
- **Files**: New `CONTRIBUTING.md`, new `CLAUDE.md`
- **Why it matters**: Required for open-source project onboarding
- **Violates core/adapters?**: No
- **Risk level**: Low
- **Strategy**: Create both files encoding core/adapter governance model
- **Validation**: Files exist and are well-formed
- **Public behavior change**: No

#### P0.4: Add architecture boundary test

- **Problem**: No automated check that core never imports adapters
- **Files**: New `tests/test_architecture_boundaries.py`
- **Why it matters**: Prevents accidental boundary violations
- **Violates core/adapters?**: No
- **Risk level**: Low
- **Strategy**: Test that `snowl.core` submodules never import from adapter packages
- **Validation**: `pytest tests/test_architecture_boundaries.py -v`
- **Public behavior change**: No

### P1 — Should Fix Soon

#### P1.1: Decouple agents from concrete OpenAICompatibleChatClient

- **Problem**: `ReActAgent` and `ChatAgent` require `OpenAICompatibleChatClient` instead of `ChatModelClient` protocol
- **Files**: `snowl/agents/react_agent.py`, `snowl/agents/chat_agent.py`
- **Why it matters**: Prevents using alternative model providers without modifying agent classes
- **Violates core/adapters?**: Yes — agents are integration layer but depend on concrete adapter
- **Risk level**: Medium (type annotation change, may affect downstream consumers)
- **Strategy**: Change `model_client: OpenAICompatibleChatClient` to `model_client: ChatModelClient`; import protocol from `snowl.model.base`
- **Validation**: `pytest tests/ -q`; `mypy snowl/agents/` (if available)
- **Public behavior change**: Type annotation only; runtime behavior unchanged since `OpenAICompatibleChatClient` satisfies `ChatModelClient`

#### P1.2: Decouple EmulatedToolWrapper from concrete client

- **Problem**: `EmulatedToolWrapper` requires `OpenAICompatibleChatClient` instead of `ChatModelClient` protocol
- **Files**: `snowl/tools/emulated_tool.py`
- **Why it matters**: Same provider coupling issue as P1.1
- **Violates core/adapters?**: Yes
- **Risk level**: Medium
- **Strategy**: Change `emulator_client: OpenAICompatibleChatClient` to `emulator_client: ChatModelClient`
- **Validation**: `pytest tests/test_emulated_tool.py -v`
- **Public behavior change**: Type annotation only

#### P1.3: ~~Remove benchmark-specific logic from runtime engine~~ RESOLVED

- **Problem**: ~~`engine.py:961` checks `output.get("osworld_score")` — benchmark-specific in generic engine~~
- **Resolution**: Replaced with generic `_get_extra_payload_keys()` that reads key names from benchmark registry at runtime. No benchmark-specific key names hardcoded in engine.
- **Files**: `snowl/runtime/engine.py`
- **Remaining concern**: Engine still does deferred import of benchmark registry (MEDIUM coupling noted in Part 1.4)

#### P1.4: ~~Remove benchmark-specific container providers from runtime~~ RESOLVED

- **Problem**: ~~`container_providers.py` imports `OSWorldContainerLauncher` from a specific benchmark~~
- **Resolution**: Container provider entry_points now use the `register_providers(registry)` convention (matching the benchmark entry_points pattern). `_discover_plugin_providers` calls `register_fn(registry)` instead of trying to instantiate provider classes with zero-arg constructors. TerminalBench and OSWorld providers from snowl-evals are now correctly discovered at runtime.
- **Files**: `snowl/runtime/container_providers.py`, `snowl-evals/snowl_evals/terminalbench/provider.py`, `snowl-evals/snowl_evals/osworld/provider.py`

#### P1.5: ~~Move AgentDojo tool implementations out of shared tools/~~ RESOLVED

- **Problem**: ~~`stateful_executor.py` contains AgentDojo banking/travel tools~~
- **Resolution**: Moved to `snowl/benchmarks/agentdojo/tools.py`. `stateful_executor.py` retains backward-compatible `__getattr__` re-exports.
- **Files**: `snowl/tools/stateful_executor.py`, `snowl/benchmarks/agentdojo/tools.py`

### P2 — Good Cleanup

#### P2.1: ~~Extract duplicated `_run_coro_sync()` to shared utility~~ RESOLVED

- **Resolution**: Created `snowl/scorer/_sync_bridge.py` with shared `run_coro_sync()`. Both `model_judge.py` and `grade_judge.py` now import from it.

#### P2.2: ~~Unify template rendering logic~~ RESOLVED

- **Resolution**: Created `snowl/scorer/_prompt.py` with shared `render_judge_prompt()`. Both `model_judge.py` and `grade_judge.py` now import from it.

#### P2.3: ~~Extract shared `_tool_schemas()` to benchmarks/utils~~ RESOLVED

- **Resolution**: Created `normalize_tool_schemas()` in `snowl/benchmarks/utils.py`. Both `bfcl/adapter.py` and `agentdojo/adapter.py` now delegate to it with `default_description_prefix` parameter.

#### P2.4: ~~Fix runtime engine latent bug in middleware injection~~ RESOLVED

- **Problem**: ~~`engine.py:779-783` calls `OpenAICompatibleChatClient(model=, base_url=, api_key=)` but constructor takes `config: OpenAICompatibleConfig`~~
- **Resolution**: Fixed to construct `OpenAICompatibleConfig` first and pass it to `OpenAICompatibleChatClient(config)`.
- **Files**: `snowl/runtime/engine.py`

#### P2.5: ~~Decouple RuntimePolicy from benchmark registry~~ RESOLVED

- **Problem**: ~~`policy.py` imports `BenchmarkConcurrencyProfile` and queries registry at runtime~~
- **Resolution**: `BenchmarkConcurrencyProfile` import moved to `TYPE_CHECKING` only. `RuntimePolicy.resolve()` now accepts `concurrency_profile` as an explicit parameter. The caller (`dispatch.py`) resolves the profile from the registry and passes it in. A fallback helper `_get_benchmark_profile_from_registry()` remains for convenience but is not called by default.
- **Files**: `snowl/runtime/policy.py`, `snowl/dispatch.py`

### P3 — Long-Term Architecture Evolution

#### P3.1: ~~Decompose CLI into subcommand modules~~ RESOLVED

- **Problem**: `cli.py` was 1,311 lines with 545 lines of duplicated helper code and inline command implementations.
- **Resolution**: Removed 545 lines of dead duplicated helpers (already in `cli_modules/`). Extracted `_cmd_quick_eval` to `cli_modules/quick_eval.py`. Moved `cli_commands.py` to `cli_modules/eval.py`. Modularized `build_parser()` into `cli_modules/parsers/` package with per-command parser builders. Result: `cli.py` reduced from 1,311 → 250 lines (thin dispatcher + backward-compat re-exports).
- **Files**: `snowl/cli.py`, `snowl/cli_modules/parsers/`, `snowl/cli_modules/quick_eval.py`, `snowl/cli_modules/eval.py`

#### P3.2: ~~Decompose runtime engine~~ RESOLVED

- **Problem**: `engine.py` was 1,751 lines as a single monolithic file.
- **Resolution**: Replaced `engine.py` with `engine/` package: `_shared.py` (data classes + 16 helpers), `prepare.py`, `execute.py`, `score.py`, `finalize.py`. `engine/__init__.py` re-exports all public symbols for backward compatibility. `from snowl.runtime.engine import X` continues to work.
- **Files**: `snowl/runtime/engine/` package (5 modules + facade)

#### P3.3: ~~Move `ChatModelClient` protocol to core~~ RESOLVED

- **Problem**: `ChatModelClient` was the sole symbol in `model/base.py`. Used by 13 files in snowl + 5 in snowl-evals.
- **Resolution**: Moved protocol definition to `snowl/core/protocols.py`. Added re-export from `snowl/core/__init__.py`. Updated `snowl/model/base.py` to backward-compat re-export from core. All existing `from snowl.model import ChatModelClient` calls continue to work.
- **Files**: `snowl/core/protocols.py`, `snowl/core/__init__.py`, `snowl/model/base.py`

#### P3.4: ~~Lazy benchmark registration~~ RESOLVED

- **Problem**: ~~`register_builtin_benchmarks()` eagerly imports all 20+ adapters~~
- **Resolution**: All adapter factory lambdas replaced with `_lazy_factory()` calls. Adapters are now imported on first use via `registry.create()`, not at module import time. Only `CsvBenchmarkAdapter` and `JsonlBenchmarkAdapter` remain eagerly imported (zero-dependency generic adapters).
- **Files**: `snowl/benchmarks/registry.py`

#### P3.5: Deprecated benchmark shim removal

- **Problem**: 14 deprecated benchmark registrations in `registry.py` still pointed to local `snowl.benchmarks.*` paths with `DeprecationWarning`s. These benchmarks have been fully migrated to snowl-evals and should be discovered via entry_points.
- **Resolution**: Removed all 14 deprecated registrations and their `warnings.warn()` blocks from `register_builtin_benchmarks()`. Plugin discovery via `_discover_plugin_benchmarks()` now handles these benchmarks from snowl-evals entry_points.
- **Files**: `snowl/benchmarks/registry.py`

### P4 — Feature Completeness

#### P4.1: Working time vs wall time separation

- **Problem**: `Timing` only had `duration_ms` (wall time). `working_time_ms` in `QuickEvalResult` fell back to wall time, so rate-limit wait/retry backoff inflated the metric.
- **Resolution**: Added `wait_time_ms: int = 0` to `Timing` dataclass with `working_time_ms` property (`duration_ms - wait_time_ms`). `OpenAICompatibleChatClient.generate()` now tracks slot admission wait and retry backoff time. `quick_eval()` uses `timing.working_time_ms`.
- **Files**: `snowl/core/task_result.py`, `snowl/model/openai_compatible.py`, `snowl/quick_eval.py`

#### P4.2: Canary auto-integration

- **Problem**: Canary stripping required manual `strip_canaries=True` opt-in in `quick_eval()`. Benchmarks that inject canaries should auto-strip.
- **Resolution**: Added `has_canary: bool = False` to `BenchmarkInfo`. Expanded `strip_canary_from_sample()` to handle `messages` format (list of dicts with `content` key). Engine's `prepare_trial_phase()` now auto-strips canaries when `_benchmark_has_canary(task)` returns True.
- **Files**: `snowl/benchmarks/base.py`, `snowl/canary.py`, `snowl/runtime/engine.py`, `snowl/benchmarks/registry.py`

#### P4.3: Friendly error on missing API key

- **Problem**: `quick_eval()` silently swallowed all exceptions. Users got no feedback when API keys were missing.
- **Resolution**: Added `first_error: str | None = None` to `QuickEvalResult`. The trial loop now captures the first exception message and includes it in the result.
- **Files**: `snowl/quick_eval.py`

#### P4.4: Missing tutorials

- **Problem**: Several docs referenced in governance checklist didn't exist yet.
- **Resolution**: Created four new tutorials: `docs/tutorials/first-eval.md`, `docs/tutorials/scoring-deep-dive.md`, `docs/tutorials/runtime.md`, `docs/tutorials/cli.md`. Updated `docs/tutorials/index.md` to include them.
- **Files**: `docs/tutorials/first-eval.md`, `docs/tutorials/scoring-deep-dive.md`, `docs/tutorials/runtime.md`, `docs/tutorials/cli.md`, `docs/tutorials/index.md`

---

## Part 4: Governance Implementation (Phase 4 Changes)

The following P0 and P1 items are safe to implement now:

### Implemented

1. **P0.1**: Replaced leaked API keys in examples with `${OPENAI_API_KEY}` placeholder
2. **P0.2**: Fixed README broken references (removed links to deleted files)
3. **P0.3**: Created `CONTRIBUTING.md` and `CLAUDE.md` with core/adapter governance
4. **P0.4**: Added `tests/test_architecture_boundaries.py` — automated check that core never imports adapters
5. **P1.1**: Decoupled `ReActAgent` and `ChatAgent` from `OpenAICompatibleChatClient` — now use `ChatModelClient` protocol
6. **P1.2**: Decoupled `EmulatedToolWrapper` from `OpenAICompatibleChatClient` — now uses `ChatModelClient` protocol
7. Fixed `test_strongreject_official_example_modules_importable` to set dummy `OPENAI_API_KEY` env var

### Intentionally Not Changed

- P1.3 (OSWorld score in engine): ~~Requires understanding OSWorld scoring pipeline deeply~~ **RESOLVED**
- P1.4 (Container provider registry): ~~Requires designing a registration API~~ **RESOLVED**: entry_points use `register_providers(registry)` convention
- P1.5 (AgentDojo tools in stateful_executor): ~~Requires coordinating with AgentDojo adapter~~ **RESOLVED**: moved to `benchmarks/agentdojo/tools.py`
- P2.3 (`_tool_schemas` duplication): **RESOLVED**: extracted to `benchmarks/utils.py:normalize_tool_schemas()`
- P2.4 (Middleware injection bug): **RESOLVED**: fixed `OpenAICompatibleChatClient` constructor call
- P2.5 (RuntimePolicy coupling): **RESOLVED**: `resolve()` accepts `concurrency_profile` parameter
- All P3 items: Deferred to subsequent PRs

---

## Part 5: Open-Source Readiness Checklist

### Must Have (P0)

- [x] No leaked secrets/keys in repo
- [x] README accurate and no broken references
- [x] CONTRIBUTING.md exists
- [x] CLAUDE.md with core/adapter governance
- [x] Architecture boundary test
- [x] Clean core layer (no adapter dependencies)
- [x] `.gitignore` prevents committing internal files

### Should Have (P1)

- [x] Agents decoupled from concrete model client
- [x] EmulatedToolWrapper decoupled from concrete model client
- [x] No benchmark-specific logic in runtime engine
- [x] No benchmark-specific imports in runtime container providers
- [x] CHANGELOG.md exists
- [x] `docs/testing.md`, `docs/development.md`, `docs/compatibility.md`, `docs/release_process.md` exist
- [x] `docs/public_api.md`, `docs/extension_points.md` exist
- [x] `.github/pull_request_template.md` exists

### Nice to Have (P2-P3)

- [x] No duplicated utilities across adapters
- [x] CLI decomposed into subcommands
- [x] Runtime engine decomposed into phases
- [x] Lazy benchmark registration
- [x] Deprecated benchmark shim removal (all 14 migrated to snowl-evals entry_points)
- [x] Public API stability test

### Feature Completeness (P4)

- [x] Working time vs wall time separation (`Timing.wait_time_ms`, `Timing.working_time_ms`)
- [x] Canary auto-integration (`BenchmarkInfo.has_canary`, engine auto-strip)
- [x] Friendly error on missing API key (`QuickEvalResult.first_error`)
- [x] Missing tutorials (first-eval, scoring-deep-dive, runtime, cli)

---

## Part 6: Validation

```bash
# Core boundary test
pytest tests/test_architecture_boundaries.py -v

# Full test suite
pytest tests/ -q

# No leaked keys
grep -r 'sk-' examples/

# Core has no adapter imports
python -c "
import importlib, pkgutil
for _, name, _ in pkgutil.iter_modules(['snowl/core']):
    mod = importlib.import_module(f'snowl.core.{name}')
    src = open(mod.__file__).read()
    for pkg in ['snowl.agents', 'snowl.model', 'snowl.benchmarks', 'snowl.scorer', 'snowl.runtime', 'snowl.tools']:
        if pkg in src:
            print(f'VIOLATION: snowl.core.{name} imports {pkg}')
"

# No broken README references
grep -E 'START_HERE|PLANS\.md|project_map|current_state' README.md
```

---

## Part 7: Recommended Next PRs

1. "Decouple agents from concrete OpenAICompatibleChatClient (use ChatModelClient protocol)"
2. "Decouple EmulatedToolWrapper from concrete model client"
3. "Remove OSWorld-specific score key check from runtime engine"
4. "Move AgentDojo tool implementations to benchmarks/agentdojo/tools.py"
5. "Fix latent bug: OpenAICompatibleChatClient constructor mismatch in engine.py middleware injection"
6. "Add CHANGELOG.md and missing governance docs (testing, development, compatibility, release_process)"
7. "Extract duplicated sync-over-async bridge from scorer modules"
8. "Decouple RuntimePolicy from benchmark registry (accept profile as parameter)"
9. "Add container provider registration mechanism to remove benchmark imports from runtime"
10. "Add public API stability test"
