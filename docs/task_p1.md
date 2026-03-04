# Snowl Phase-2 Tasks (P1)

Goal: benchmark-centric ecosystem adaptation, with runtime scalability as a support track.

## 0. Critical Decision

P1 mainline is not "generic adapter breadth first".  
P1 mainline is "three target benchmarks end-to-end first":

1. OSWorld
2. terminalbench
3. strongreject

Reason:

1. These three represent three distinct eval realities:
- GUI + multimodal + container (OSWorld)
- terminal + tool execution + container (terminalbench)
- no-container safety eval + judge-style scoring (strongreject)
2. If Snowl can stably support these three, missing abstractions in Task/Env/Tool/Scorer contracts will surface naturally.
3. Pure runtime/perf work without real benchmark pressure is likely to optimize the wrong bottlenecks.

---

## 1. Non-Negotiable Principles (Hard Constraints)

These are hard constraints for all P1 tasks.

1. Semantic alignment over full fidelity.
- Primary target is alignment with benchmark task-loading semantics and scorer rules.
- Full implementation fidelity to upstream benchmark internals is NOT required.
- Do not spend time reproducing benchmark-specific quirks unless they affect task schema loading or scoring semantics.

2. No dependency on benchmark packages.
- Do not import or rely on OSWorld / terminalbench / strongreject packages at runtime.
- Port required logic into Snowl codebase.
- Benchmark code lives under `snowl/benchmarks/<benchmark_name>/`.

3. Adaptation scope is strict.
- Only adapt Task (+ corresponding Env), Scorer, and required built-in tools.
- Built-in tools live under `snowl/tools/`.

4. Official-agent runnable examples are mandatory.
- For each benchmark, port official reference agent behavior into:
  - `examples/<benchmark_name>-official/`
- Target references:
  - OSWorld: `references/OSWorld/mm_agents/qwen3vl_agent.py`
  - terminalbench: `references/terminal-bench/terminal_bench/agents/terminus_1.py`
- Goal: user can directly run those examples for real testing.

5. Scorer commonality must be extracted.
- Reusable scorer capabilities go into `snowl/scorer/` (shared library), not buried in benchmark adapters.

---

## 2. Exit Criteria (P1 Done Definition)

P1 is done when all are true:

1. `snowl bench run osworld ...` works with Snowl-native adapter, env, scorer, tools.
2. `snowl bench run terminalbench ...` works with Snowl-native adapter, env, scorer, tools.
3. `snowl bench run strongreject ...` works with Snowl-native adapter, scorer (no container).
4. `examples/osworld-official`, `examples/terminalbench-official`, `examples/strongreject-official` run via `snowl eval`.
5. `snowl/scorer/` provides reusable scorers:
- `includes()`
- `match()`
- `pattern()`
- `model_as_judge_json(model_name=..., system_prompt=...)`
6. Runtime supports stable concurrent execution for container-heavy benchmarks with bounded resources and resume safety.
7. AgentVariant is first-class and production-usable for both multi-implementation and multi-model comparisons.
8. Live CLI (Claude Code-like) is production-usable for long eval runs, compare workflows, and interactive control.
9. OSWorld and terminalbench run in real containerized execution (not mock/skeleton), including agent action loop and test execution.
10. Every eval run emits a complete `.log` file; CLI live view must expose container startup/config details for debugging.

---

## 3. Workstreams

## 3.1 Benchmark Vertical Slices (Mainline, P0 in P1)

### 3.1.1 OSWorld Slice
- [ ] Implement `snowl/benchmarks/osworld/` adapter and dataset loader (Snowl-native, no upstream dependency).
- [ ] Define OSWorld Task schema mapping:
- instruction, multimodal observation config, action space, max steps, domain/example identity.
- [ ] Implement OSWorld env in `snowl/envs/`:
- GUI container/VM execution contract, screenshot/a11y observation channel, action execution ops.
- [ ] Implement required built-in GUI tools in `snowl/tools/` (click/type/key/scroll/wait/terminate primitives).
- [ ] Implement OSWorld scorer in `snowl/scorer/` and benchmark wrapper scorer.
- [ ] Port official-agent behavior into `examples/osworld-official/agent.py` with Snowl ReAct-compatible interface.
- [ ] Add end-to-end integration tests and benchmark conformance tests.

### 3.1.2 terminalbench Slice
- [ ] Implement `snowl/benchmarks/terminalbench/` adapter and registry integration.
- [ ] Define terminalbench Task schema mapping:
- instruction, task metadata, terminal image/spec, timeout/episode controls.
- [ ] Implement terminal container env in `snowl/envs/`:
- command execution, tmux-like session abstraction, terminal snapshot capture.
- [ ] Implement required built-in terminal tools in `snowl/tools/`:
- send_keys/exec, blocking wait, pane capture, timeout handling primitives.
- [ ] Implement terminalbench scorer in `snowl/scorer/` and benchmark wrapper scorer.
- [ ] Port official-agent behavior into `examples/terminalbench-official/agent.py` aligned to Snowl ReAct loop.
- [ ] Add end-to-end integration tests and benchmark conformance tests.

### 3.1.3 strongreject Slice
- [ ] Implement `snowl/benchmarks/strongreject/` adapter (no-container path).
- [ ] Define strongreject Task schema mapping:
- forbidden prompt input, jailbreak template metadata, sample id determinism.
- [ ] Implement strongreject scorer pipeline using shared judge scorers.
- [ ] Port reference runner behavior into `examples/strongreject-official/`:
- task + agent + scorer with Snowl-native interfaces.
- [ ] Add integration tests with deterministic output schema and judge parse robustness.

---

## 3.2 Shared Scorer Library (P0 in P1)

Create `snowl/scorer/` as reusable scorer library.

### 3.2.1 Text Match Family (inspect.ai-inspired)
- [ ] `includes(case_sensitive=False)`
- [ ] `match(position="end|start", ignore_case=True, ignore_whitespace=True, ignore_punctuation=True)`
- [ ] `pattern(regex, group=0, flags=...)`

### 3.2.2 Model-as-a-Judge
- [ ] `model_as_judge_json(model_name: str, system_prompt: str, schema: dict | None = None)`
- [ ] Prompt rendering uses placeholder replacement from `task_result/payload/context/trace`; no output/target extractor arguments.
- [ ] Enforce JSON output validation and structured parse errors.
- [ ] Save judge prompt/input/output and parsed fields into scorer provenance artifacts.

### 3.2.3 Composition
- [ ] Weighted composite scorer.
- [ ] Multi-scorer chaining with metric namespace isolation.
- [ ] Failure-tolerant scorer execution (partial metric preservation).

---

## 3.3 Runtime and Engine Support (Support Track, P1 in P1)

### 3.3.1 Concurrency and Backpressure
- [ ] Explicit concurrency controls:
- `max_trials`, `max_sandboxes`, `max_builds`, `max_model_calls`.
- [ ] Queueing and fair scheduling across benchmark/task groups.
- [ ] Pool health telemetry for containerized env runs.

### 3.3.2 Reliability for Heavy Benchmarks
- [ ] Checkpoint granularity improvements for long-running benchmark runs.
- [ ] Resume correctness tests under partial failures.
- [ ] Failure diagnostics bundles for env/tool/model/scorer phases.
- [ ] Mandatory full run log artifact (`.log`) for every `snowl eval` / `snowl bench run`.

### 3.3.3 Performance Baselines
- [ ] Throughput baselines for OSWorld/terminalbench representative workloads.
- [ ] Artifact I/O efficiency improvements for large matrix runs.
- [ ] Regression guard tests for runtime slowdowns.

---

## 3.4 Example System (P0 in P1)

All examples must be top-level `examples/` folders.

- [ ] `examples/osworld-official/`
- [ ] `examples/terminalbench-official/`
- [ ] `examples/strongreject-official/`

Each example folder must include:

- `task.py`
- `agent.py`
- `scorer.py`
- optional `tool.py`
- `README.md` with exact run command and required env vars

---

## 3.5 AgentVariant First-Class UX (Final Stage in P1)

Goal: unify "multiple agent implementations" and "same scaffold with multiple models"
under one reliable, low-friction user experience.

- [ ] Introduce `AgentVariant` schema with stable identity:
- `agent_id`, `variant_id`, `model`, `params`, optional provenance metadata.
- [ ] Make runtime identity and artifacts variant-aware:
- trial identity includes `variant_id`; resume/checkpoint/rerun semantics remain deterministic.
- [ ] Add first-class discovery and loading:
- allow `agent.py` to export variants directly; support scaffold-defined model grids.
- [ ] Add variant-focused CLI UX:
- `--agent`, `--variant`, and compact compare filters with sane defaults.
- [ ] Add report/TUI compare views:
- group by `agent_id` / `variant_id` / `model`, with stable sort and clear labels.
- [ ] Add reliability/perf protections for variant sweeps:
- per-variant failure isolation, bounded fan-out, and actionable diagnostics.
- [ ] Add end-to-end tests and examples:
- validate matrix expansion, artifact schema, resume correctness, and comparison output quality.

---

## 3.6 Decorator-Based Authoring (Final Stage in P1)

Goal: unify authoring UX with explicit decorators for stable discovery and ids.

- [ ] Add `@task`, `@agent`, `@scorer` decorators in core API.
- [ ] Move `task_id/agent_id/scorer_id` to decorator-first assignment with backward compatibility.
- [ ] Standardize autodiscovery priority:
- decorated objects first, then protocol-based fallback discovery.
- [ ] Add example migration:
- update benchmark examples to decorator style without wrapper boilerplate.
- [ ] Add validation and conflict checks:
- duplicate ids, missing ids, and mixed declaration ambiguity.

---

## 3.7 Advanced Live CLI (Final Stage in P1)

Goal: deliver a high-quality, interactive terminal UX for eval runs, close to Claude Code live workflow quality.

- [ ] Build live run dashboard with multi-panel layout:
- global progress, active trials, event stream, variant compare board, and failure list.
- [ ] Add interactive controls and command palette:
- pause/resume, focus failed-only, rerun failed, filter task/agent/variant, and quick jump.
- [ ] Add rich streaming output:
- incremental trace events, tool/action updates, scorer/judge events, and sandbox diagnostics.
- [ ] Show container startup/config lifecycle in live UI:
- build/pull image info, compose/env config snapshot, container ids, health/startup stages.
- [ ] Make compare UX first-class in terminal:
- group/sort by task/agent/variant/model and show deltas in-session.
- [ ] Add robust keyboard + non-interactive parity:
- every interactive action has deterministic CLI/no-ui equivalent.
- [ ] Improve visual quality and readability:
- stable layout, compact density modes, clear colors/symbols, and low-noise defaults.
- [ ] Add reliability/performance guards:
- UI refresh throttling, bounded buffers, and graceful degradation on large runs.
- [ ] Add UX snapshot tests and demo scripts:
- reproducible terminal snapshots and one-command demo for project showcase.

---

## 4. Implementation Order (Fastest P1 Value Path)

1. Build shared `snowl/scorer/` primitives (`includes/match/pattern/model_as_judge_json`).
2. Implement strongreject vertical slice first (no-container, fast validation loop).
3. Implement terminalbench vertical slice (terminal container complexity).
4. Implement OSWorld vertical slice (GUI + multimodal complexity).
5. Harden runtime concurrency/backpressure based on measured bottlenecks from real runs.
6. Finalize official examples and conformance/stability suites.
7. Implement and harden first-class `AgentVariant` UX (schema + runtime + CLI + reports).
8. Implement decorator-based authoring and discovery (`@task/@agent/@scorer`).
9. Implement and harden advanced Live CLI experience for showcase-quality demos.
10. Complete real containerized execution parity for terminalbench and OSWorld (agent loop + test path + diagnostics).

---

## 5. Risks and Mitigations

1. Risk: "No upstream dependency" increases maintenance burden.
- Mitigation: port minimal needed logic only; isolate ports in benchmark folders with attribution docs.

2. Risk: OSWorld/terminalbench env complexity can stall delivery.
- Mitigation: strict vertical slicing with thin env contracts first, then incremental fidelity.

3. Risk: model-as-judge instability harms scorer trust.
- Mitigation: JSON schema validation, parse-failure taxonomy, provenance artifact persistence.

4. Risk: official-agent behavior drift after porting.
- Mitigation: parity tests against reference traces on fixed seed subsets.

---

## 6. Deliverables

- `snowl/benchmarks/osworld/`
- `snowl/benchmarks/terminalbench/`
- `snowl/benchmarks/strongreject/`
- `snowl/tools/` built-in GUI/terminal helpers required by benchmark slices
- `snowl/scorer/` shared scorer library
- `examples/osworld-official/`
- `examples/terminalbench-official/`
- `examples/strongreject-official/`
- `AgentVariant` schema/runtime/CLI/report support
- Advanced Live CLI + interactive compare experience
- Real containerized execution path for terminalbench and OSWorld
- Full eval run `.log` artifact for every run
- `outcome_p1.md`
