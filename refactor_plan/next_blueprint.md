# Snowl Architecture Review & Evolution Blueprint

**Author**: Chief Architect
**Date**: 2026-05-13
**Scope**: Full-stack review of snowl v0.1.0 → v0.2.0 evolution

---

## 1. Current Architecture Snapshot

| Dimension | Metric |
|-----------|--------|
| Source lines | 31,035 (Python) |
| Test lines | 14,409 |
| Core deps | 4 (httpx, PyYAML, requests, rich) |
| Public API symbols | 16 |
| Benchmark adapters | 20+ |
| Scorer types | 10 |
| Iterations completed | 4 (AsyncScorer, ConcurrencyProfile, ToolMiddleware, EmulatedToolWrapper) |

**What works well:**
- Protocol-based core contracts (Agent, Scorer, Task) — clean separation of concerns
- Four-phase trial lifecycle (prepare → execute → score → finalize) with progressive result types
- ResourceScheduler with provider admission, phase semaphores, and sandbox slot tracking
- Benchmark adapter template-method pattern — easy to add new benchmarks
- V1+V2 aggregation with risk index computation
- Minimal core dependency profile

---

## 2. Critical Architecture Problems

### P1. eval.py is a 1850-line god module

`eval.py` contains: component discovery, autodiscovery, checkpoint management, retry orchestration, interaction control, web monitor sidecar, container lifecycle setup, provider budget resolution, profiling, and two complete retry paths. The core function `run_eval_with_components()` is 780 lines with 31 parameters.

**Why it matters**: Any change to discovery, dispatch, or reporting requires understanding the entire function. It is the single highest-risk file in the codebase.

**Specific pain points**:
- `_discover_agents()` is 120 lines with nested closures capturing mutable state — untestable in isolation
- The main dispatch loop (`eval.py:1408-1476`) hand-rolls priority scheduling that duplicates ResourceScheduler concerns
- Two `retry_run` paths (bench source + eval source) repeat ~200 lines of identical logic

**Recommendation**: Decompose into `snowl/discovery.py`, `snowl/dispatch.py`, `snowl/retry.py`. The eval entry point becomes a thin compose-and-run shell.

### P2. Single-scorer hardwiring

The pipeline only supports one scorer per run. The constraint spans 7 files:

| Location | Pattern |
|----------|---------|
| `eval.py:1684` | `scorer=components.scorers[0]` — silently discards others |
| `eval.py:859` | `scorer: Scorer` parameter — singular |
| `engine.py:60` | `TrialRequest.scorer: Scorer` — singular |
| `engine.py:1013-1016` | `score_trial_phase` calls one scorer |
| `eval_loop.py:55` | `EvalTrialLifecycle.scorer` — singular |
| `planning.py` | Plan expansion has no scorer dimension |

**Why it matters**: Multi-scorer evaluation (accuracy + safety + latency) is a fundamental need. Currently requires manual `ChainedScorer` composition, which breaks provider admission for async scorers.

**Recommendation**: Change to `scorers: list[Scorer]`, loop in `score_trial_phase`, add `scorer_id` to plan dimensions.

### P3. `__snowl_*` metadata smuggling in AgentContext

Runtime internals are injected into `AgentContext.metadata` via private-key conventions:

| Key | Injected at | Purpose |
|-----|-------------|---------|
| `__snowl_emit_event` | `engine.py:433` | Event emission callback |
| `__snowl_container_session` | `engine.py:555` | Container session handle |
| `__snowl_workspace` | `engine.py:474` | Workspace reference |
| `__snowl_runtime_container_spec` | `engine.py:557` | Container spec |

**Why it matters**: The `AgentContext` contract is `metadata: dict[str, Any]` — agents can see and accidentally depend on these private keys. This is an abstraction leak between core and runtime that will ossify.

**Recommendation**: Add typed optional fields to `AgentContext` (or introduce `RuntimeContext` as a separate parameter): `emit_event: Callable | None`, `workspace: Any | None`, `container_session: Any | None`. Remove private-key smuggling.

### P4. No agent routing strategy

The runtime unconditionally calls `request.agent.run(state, context, tools)` (engine.py:774). There is no dispatch point for native vs emulated vs stateful execution. `AgentVariantAdapter` carries `params` and `provenance` but the runtime never inspects them.

**Why it matters**: ToolEmuEmulationAgent and the future StatefulToolExecutor each bypass the standard pipeline in ad-hoc ways. Each new execution paradigm requires a custom workaround rather than a pluggable strategy.

**Recommendation**: Add an `execution_mode` field to `AgentVariant` (or `TrialRequest`). In `execute_agent_phase`, dispatch based on mode: `native` → direct `agent.run()`, `emulated` → wrap with `EmulatedToolWrapper`, `stateful` → wrap with `StatefulToolExecutor`. This makes middleware composition declarative.

### P5. Scorer composition doesn't support AsyncScorer

`ChainedScorer` and `WeightedCompositeScorer` only implement `score()`, not `ascore()`. Chaining a `ModelAsJudgeJSONScorer` inside a `ChainedScorer` forces the sync `score()` path, which uses `_run_coro_sync` (spawns a thread) and bypasses provider admission.

**Why it matters**: This is a correctness issue — LM-based scorers in chains consume provider budget without admission control, potentially overwhelming rate limits.

**Recommendation**: Add `AsyncChainedScorer` and `AsyncWeightedCompositeScorer` (or upgrade the existing ones) that delegate to `ascore` when available.

### P6. Benchmark registry eager-imports all adapters

`register_builtin_benchmarks()` at module scope imports 20+ adapter modules, which transitively import `datasets`, `pandas`, `beautifulsoup4`, etc. Users who only need one benchmark pay the startup cost of all.

**Why it matters**: Import time and dependency surface. Every optional dependency becomes effectively required.

**Recommendation**: Lazy registration — store `{name: module_path}` in the registry, import on first `create()`.

---

## 3. Medium-Priority Design Debt

### D1. prepare_trial_phase is a 360-line function

8 distinct early-return error paths, all constructing `PreparedTrial` with slight variations. Mixed concerns: workspace + container + tools + sandbox preparation.

**Fix**: Extract `resolve_workspace()`, `resolve_container()`, `resolve_tools()`, `prepare_sandbox()` sub-functions returning result-or-error types.

### D2. ReActAgent and ChatAgent duplicate model I/O event emission

~80 lines of identical `runtime.model.io` / `runtime.model.query.*` event construction in each agent. Adding a new agent type means copying this boilerplate.

**Fix**: Extract `ModelIOWrapper` that wraps `ChatModelClient.generate` and emits events. Agents call `self._io_wrapper.generate(messages)` instead of `self.model_client.generate(messages)`.

### D3. ReActAgent._execute_tool_call doesn't use ToolSpec.execute()

It directly calls `tool_fn(**parsed_args)`, missing the `async_callable` path added in Iteration 3.

**Fix**: Change to use `ToolSpec.execute()` when tool specs are available, falling back to `tool_fn` only for the legacy `tool_map` path.

### D4. CLI flag duplication

25+ UI/runtime flags are defined three times across `eval`, `retry`, and `bench run` subcommands. The "run with monitor" pattern is a 40-line block repeated 3 times.

**Fix**: Extract shared flag factory and `_run_with_monitor()` helper.

### D5. Metadata lost from TaskResult payload

`engine.py:879-882` copies only 5 hardcoded keys (`benchmark`, `domain`, `benchmark_type`, `family`, `primary_metric`) from task metadata to TaskResult payload. Custom metadata is silently dropped.

**Fix**: Copy all task metadata keys, or add a `task_metadata` field to `TaskResult`.

### D6. `accuracy < 1.0 → INCORRECT` hardcoded in score_trial_phase

A business rule baked into framework plumbing at `engine.py:1072-1090`. Different benchmarks have different correctness criteria.

**Fix**: Move to `Task.metadata["incorrect_threshold"]` or scorer-level status override, not in the engine.

### D7. Dual HTTP client dependency

Both `httpx` (async) and `requests` (sync) are core dependencies. They serve overlapping purposes.

**Fix**: Standardize on `httpx` for async paths; evaluate whether `requests` can be removed from core.

### D8. No environment variable substitution in project.yml

API keys and URLs must be hardcoded in YAML. No `${env:VAR}` or `${VAR}` syntax.

**Fix**: Add `StringSubstitution` preprocessor for `project.yml` values that resolves `${VAR}` and `${env:VAR}` references.

---

## 4. Missing Capabilities for Production Readiness

### M1. Multi-scorer pipeline
Required for: combined accuracy+safety+latency evaluation, per-scorer provider budgets, AgentDojo paired evaluation.
**Scope**: TrialRequest, score_trial_phase, PlanBuilder, eval.py.

### M2. Deferred scoring + `snowl rescore`
Required for: `--no-score` fast runs, post-hoc rescoring with different scorers, human-in-the-loop review.
**Scope**: New `DeferredScoringManager`, engine `skip_scoring` parameter, CLI `rescore` subcommand.

### M3. Agent routing by execution mode
Required for: declarative native/emulated/stateful selection without custom agent.py files.
**Scope**: AgentVariant, execute_agent_phase, project.yml schema.

### M4. MetricAggregator with configurable strategies
Required for: per-metric aggregation strategy (mean, max, percentile), grouped breakdowns, stderr.
**Scope**: New `snowl/metrics/` module, integration with aggregator.

### M5. Rich report generation
Required for: usable HTML report with charts, model comparison, risk indices, per-trial drilldowns. Current report is 15 lines of f-string HTML.
**Scope**: Template-based HTML generator, chart library (plotly/matplotlib), `snowl report <run_id>` CLI command.

### M6. Cross-run comparison
Required for: experiment tracking, A/B comparison across models/versions.
**Scope**: `--experiment-id` based aggregation, `snowl compare <run1> <run2>` command.

### M7. StatefulToolExecutor + InjectionMiddleware
Required for: AgentDojo benchmark integration.
**Scope**: New `snowl/tools/stateful_executor.py`, `snowl/tools/injection.py`, PairedEvaluationSpec.

---

## 5. Evolution Roadmap: v0.1.0 → v0.2.0

### Phase 0: Stabilization (current, ~60% complete)

| Work | Status |
|------|--------|
| AsyncScorer protocol | ✅ Done |
| BenchmarkConcurrencyProfile | ✅ Done |
| ToolMiddleware + MiddlewareChain | ✅ Done |
| EmulatedToolWrapper | ✅ Done |
| ToolEmu eval pipeline integration | 🔄 Phase A in progress |
| AgentDojo StatefulToolExecutor | ❌ Pending |

### Phase 1: Structural Decomposition

**Priority**: High. Reduces risk for all subsequent work.

| Task | Effort | Impact |
|------|--------|--------|
| Decompose eval.py into discovery/dispatch/retry modules | 3-4 days | Unblocks all pipeline changes |
| Fix __snowl_* metadata smuggling → typed AgentContext fields | 1-2 days | Clean core/runtime boundary |
| Extract ModelIOWrapper from agent event emission | 1 day | DRY, unblocks new agent types |
| Fix ReActAgent to use ToolSpec.execute() | 0.5 day | Completes Iteration 3 contract |
| Lazy benchmark registry | 1 day | Faster startup, smaller dependency surface |

### Phase 2: Multi-Scorer Pipeline

**Priority**: High. Required for paired evaluation and per-scorer provider budgets.

| Task | Effort | Impact |
|------|--------|--------|
| TrialRequest.scorers: list[Scorer] | 2 days | Core data model change |
| score_trial_phase loops over scorers | 1 day | Engine change |
| AsyncChainedScorer + AsyncWeightedCompositeScorer | 1 day | Composition fix |
| PlanBuilder scorer dimension | 1 day | Planning change |
| CLI --scorer flag | 0.5 day | UX |

### Phase 3: Agent Routing & Declarative Config

**Priority**: Medium. Required for zero-code benchmark setup.

| Task | Effort | Impact |
|------|--------|--------|
| AgentVariant.execution_mode field | 1 day | Routing foundation |
| execute_agent_phase dispatch by mode | 1 day | Engine dispatch |
| project.yml `agent.type` + middleware config | 1 day | Declarative setup |
| Middleware auto-wiring from benchmark profile | 1 day | Benchmark-driven config |

### Phase 4: Reporting & Observability

**Priority**: Medium. Required for production usability.

| Task | Effort | Impact |
|------|--------|--------|
| MetricAggregator with configurable strategies | 2 days | stderr, grouped breakdowns |
| Template-based HTML report with charts | 3 days | Usable reports |
| `snowl report <run_id>` command | 1 day | Standalone report generation |
| `snowl compare <run1> <run2>` | 1 day | Cross-run comparison |
| Structured Trace dataclass | 1 day | Type-safe trace model |

### Phase 5: AgentDojo Full Integration

**Priority**: Medium. Depends on Phase 2 (multi-scorer) and Phase 3 (agent routing).

| Task | Effort | Impact |
|------|--------|--------|
| StatefulToolExecutor middleware | 2-3 days | Stateful tool execution |
| InjectionMiddleware | 1-2 days | Attack injection |
| PairedEvaluationSpec | 1 day | Clean/attacked paired scoring |
| AgentDojo example project | 1 day | End-to-end validation |

### Phase 6: Polish & Hardening

| Task | Effort | Impact |
|------|--------|--------|
| Environment variable substitution in project.yml | 0.5 day | Security + convenience |
| Remove requests dependency | 1 day | Dependency cleanup |
| Add mypy/pyright to CI | 1 day | Type safety |
| Test reorganization (unit/ + integration/) | 1 day | Faster CI |
| Deferred scoring + snowl rescore | 2 days | Flexible scoring workflow |
| CLI flag DRY refactor | 1 day | Maintainability |
| Metadata propagation fix (5-key allowlist → full copy) | 0.5 day | Scorer access to task metadata |
| Move accuracy threshold out of engine | 0.5 day | Business rule extraction |

---

## 6. Architecture Principles for v0.2.0

1. **Decompose before extending**. The 1850-line eval.py is the bottleneck for all pipeline changes. Decompose it first.

2. **Protocol over inheritance**. The ToolMiddleware pattern works well. Apply the same principle to execution strategies, report generators, and metric aggregators.

3. **Typed contracts over dict bags**. Replace `metadata: dict[str, Any]` smuggling with typed fields. Every `__snowl_*` key is a design failure.

4. **Lazy over eager**. The benchmark registry, adapter imports, and sample materialization should all be lazy. Pay only for what you use.

5. **Composition over hardwiring**. Multi-scorer, agent routing, and middleware auto-wiring should be composable rather than baked into the pipeline.

6. **Provider admission is non-negotiable**. Every LM call (agent, emulator, scorer, critiquer) must go through provider admission. The current gap in ChainedScorer is a correctness bug, not a style issue.

7. **Configurability through data, not code**. A user should be able to run ToolEmu emulation without writing Python — just `project.yml` with `agent.type: emulated` and benchmark profile. Code modules are the escape hatch, not the default.

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| eval.py decomposition introduces regressions | High | High | Comprehensive integration tests before refactor; small PRs |
| Multi-scorer change breaks existing scorer users | Medium | High | Backward compat: single scorer auto-wrapped into list |
| Agent routing adds framework complexity | Medium | Medium | Keep routing optional; default to `native` |
| HTML report template becomes unmaintainable | Low | Medium | Use established template engine (Jinja2) |
| Provider admission gap causes rate limit errors in production | High | High | Fix ChainedScorer async support first |

---

## 8. Success Criteria for v0.2.0

1. `snowl eval examples/toolemu-emulation/project.yml` runs end-to-end with LM emulation, produces outcomes + rich HTML report
2. `snowl eval examples/agentdojo/project.yml` runs end-to-end with stateful tools + injection, produces paired evaluation scores
3. No file exceeds 500 lines (except eval.py decomposition artifacts which should each be <300)
4. Zero `__snowl_*` keys in AgentContext.metadata — all typed fields
5. Multi-scorer pipeline: `project.yml` lists multiple scorers, each gets provider admission
6. `snowl report <run_id>` regenerates reports from existing artifacts
7. `snowl compare` shows cross-run diffs
8. All LM calls go through provider admission (including chained scorer LM calls)
9. Benchmark registry lazy-loads adapters
10. Zero hardcoded business rules in engine (accuracy threshold, metadata allowlist)
