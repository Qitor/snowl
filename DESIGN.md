# Snowl Design v0302

## 1. Design Goal

Snowl is a general agent evaluation framework centered on a simple user promise:

- Users define what to test, not how to orchestrate execution.
- The framework hides execution complexity (especially environment/container lifecycle).
- A minimal default flow should run with one command.

Primary command experience:

```bash
snowl eval ...
```

---

## 2. Core Paradigm: Task + Agent + Scorer

Snowl's first-class evaluation unit is not only `Task`, but a `Task x Agent` trial.

- `Task`: What problem/environment/constraints to solve.
- `Agent`: How to solve it (implementation/framework/model/scaffold strategy).
- `Scorer`: How to evaluate trial outputs (can output multiple metrics).

Benchmark support is treated as a Task source (provider), not the center of the runtime model.

---

## 3. Minimal User Contract (3 Files)

A user can run evals by implementing:

- `task.py`
- `agent.py`
- `scorer.py`

After these are implemented, `snowl eval ...` should run without requiring heavy config.

### 3.1 Task Schema (required)

Task must declare execution intent and environment needs.

Required fields/capabilities:

- `task_id`
- `env_spec` (or `sandbox_spec`): declare required runtime environment
- sample loader (`iter_samples()` / `load_samples()`)
- optional metadata

### 3.2 Agent Schema (required)

Agent must be framework-agnostic at contract level so adapters for major ecosystems can be added later.

Required fields/capabilities:

- `agent_id`
- unified run interface (accept task input + env/tools context)
- trace hooks (for observability and scorer support)

### 3.3 Tool Schema (required if tools are used)

Tool must explicitly declare environment operation requirements.

Required fields/capabilities:

- `tool_name`
- `required_ops`
- callable interface

### 3.4 Env Schema (required)

Environment exposes operation capabilities.

Required fields/capabilities:

- `env_id`
- `provided_ops` (e.g., `FileOps`, `ProcessOps`, `WebOps`)
- lifecycle interface (`prepare/reset/step/close` or equivalent)

Compatibility rule:

- `tool.required_ops` must be a subset of `env.provided_ops`.

### 3.5 Scorer Schema (required)

Scorer input should be stable and composable:

- input: `TaskResult + Trace (+ Task/Sample metadata)`
- output: `dict[str, Score]` (multiple metrics allowed)

### 3.6 Model-as-Judge Prompt Contract

`model_as_judge_json` uses template placeholder replacement only (no extractor args).

Design rules:

- Scorer users write `system_prompt` and `user_prompt` templates directly.
- Snowl replaces `{placeholder}` with values from runtime variables.
- Unknown placeholders:
- raise error when `strict_templates=True`
- remain unchanged when `strict_templates=False`

Template variable pool:

- `task_result` (full TaskResult dict)
- `payload` (`task_result.payload`)
- `context` (`ScoreContext` dict)
- `trace` (trial trace dict)
- convenience aliases from task_result/payload/context top-level keys
- `output` (best-effort from `task_result.final_output.content/message.content`)
- `target` (best-effort from `context.sample_metadata` / `context.task_metadata`)
- `schema`, `schema_json`

Example:

```text
System: You are a strict evaluator.
User: Prompt={payload.prompt}
      Response={payload.response}
      Context={context.task_id}
```

---

## 4. TaskResult Schema Strategy

TaskResult should **not** be fully user-defined.

Use a two-layer structure:

1. Fixed core layer (framework-owned, stable)
- `status`
- `final_output`
- `error`
- `timing`
- `usage`
- `artifacts`
- `task_id` / `agent_id` / `sample_id` / `seed`

2. Extensible payload layer (user-owned)
- `payload: dict[str, Any]`

This keeps Scorer/Aggregator stable while preserving benchmark/domain extensibility.

---

## 5. UX Principles

### 5.1 Default-Simple, Advanced-Controllable

- Default path: no YAML required.
- Advanced path: optional config/YAML for reproducible experiment control.

### 5.2 Auto Discovery + Auto Planning

By default, `snowl eval .` should discover tasks/agents/scorers and auto-expand evaluation plan.

Suggested expansion rules:

- 1 Task x 1 AgentVariant: single run
- N Task x 1 AgentVariant: task sweep
- 1 Task x M AgentVariants: agent/model comparison
- N Task x M AgentVariants: full matrix

### 5.3 Keep CLI Surface Small

Default command should remain clean.

High-frequency optional selectors only:

- `--task`
- `--agent`
- `--split`
- `--limit`
- `--seed`

---

## 6. Agent Variant Model (for comparison UX)

To unify "multiple agent implementations" and "same scaffold with multiple models", introduce `AgentVariant` as a first-class concept.

Suggested identity:

- `agent_id` (base scaffold/implementation)
- `variant_id` (specific config)
- `model`
- `params` (prompt/tools/runtime knobs)

This allows one consistent UX for:

- comparing different agent implementations
- comparing model choices under one scaffold

---

## 7. Benchmark as TaskProvider

A benchmark should be treated as a `TaskProvider` that yields homogeneous Task schema instances.

Suggested contract:

- `list_splits()`
- `count(split)`
- `iter_tasks(split, filters)` (lazy)
- `get_task(task_id)`

Design goals:

- lazy loading (avoid loading all tasks into memory)
- easy mapping from benchmark rows to Task schema
- reusable adapters for common formats (JSONL/CSV/Parquet/HF)

---

## 8. Container and Environment Complexity (Hidden from Users)

In agent evaluation, many tasks have task-specific container specs. This complexity must be absorbed by runtime.

### 8.1 SandboxSpec + Hashing

- Every task provides a normalized `SandboxSpec`.
- Runtime computes `spec_hash` for deduplication/reuse.

### 8.2 Two-Phase Lifecycle

- `prepare`: build/pull/setup assets
- `run`: start/exec/teardown

This enables prewarming and reduces inline startup cost.

### 8.3 Warm Pool

Maintain reusable sandbox pools keyed by `spec_hash`.

### 8.4 Concurrency Governance

Control separately:

- `max_sandboxes`
- `max_builds`
- `max_samples`

Avoid resource storms and unstable runs.

### 8.5 Failure Recovery

- retain recoverable trial progress
- retry without repeating expensive prepare steps when possible
- persist environment diagnostics for debugging

### 8.6 Observability

For each trial, record:

- `spec_hash`
- build/pull identifiers
- container/session IDs
- startup latency
- teardown reason

---

## 9. Reproducibility and Resume (Must-Have)

Define a run manifest with stable identity fields:

- dataset fingerprint
- task/agent/scorer version IDs
- model exact version
- seed/epoch
- env image digest/spec hash

Resume semantics:

- trial-level resumability
- sample-level recovery where applicable
- deterministic identity for reruns

---

## 10. Recommended Evaluation Modes

1. Local file mode
- user-authored `task.py + agent.py + scorer.py`

2. Benchmark mode
- adapter/provider converts benchmark rows into Task instances

3. Matrix mode
- explicit or auto-expanded Task x AgentVariant experiments

All modes should use the same runtime and output schema.

---

## 11. Non-Goals (for this version)

- Do not require users to learn container orchestration details.
- Do not force YAML for first run.
- Do not allow benchmark-specific logic to leak into core contracts.

---

## 12. v0302 Summary

Snowl v0302 prioritizes product usability under real agent-eval complexity:

- Strong core abstraction: `Task + Agent + Scorer`
- Minimal first-run UX: define and run
- First-class comparison UX via `AgentVariant`
- Benchmark integration via `TaskProvider`
- Runtime-managed container complexity with reuse and recovery
- Stable result contracts for multi-metric scoring and aggregation

---

## 13. Product UX and Ecosystem Goals (P0)

These are not optional enhancements. They are core product goals for MVP direction.

### 13.1 UX-First CLI/TUI

The default `snowl eval ...` experience should be visually strong, interactive, and informative.

Required UX properties:

- beautiful and readable terminal presentation by default
- real-time progress and status visibility
- interactive filtering/grouping/retry controls
- clear end-of-run summary and reproducible rerun hint

Recommended live views:

1. Global view
- total progress
- pass/fail/error counts
- token/cost/time summaries
- sandbox/container pool status

2. Trial view
- active `task x agent_variant` runs
- latest tool/action traces
- failure reasons and retry state

3. Compare view
- live leaderboard by metrics from `scorer.py`
- grouping by task / agent / model

### 13.2 Powerful Ecosystem Adaptation

Snowl should support one-command evaluation against third-party benchmarks and frameworks.

Required capabilities:

- benchmark registry and discoverability (`snowl bench list`)
- one-command benchmark execution (`snowl bench run <name> ...`)
- adapter conformance checks for quality control
- pluginized loading for benchmark and framework adapters

### 13.3 MVP Model Scope

For MVP, model integration is intentionally constrained:

- only OpenAI-compatible model interface is required
- support custom base URL + key + model name
- prioritize real run/test reliability over provider breadth

Provider-specific adapters can be added later without changing core contracts.

---

## 14. Agent Module Strategy (MVP)

Question: if model scope is limited to OpenAI-compatible first, what should Agent module do?

Answer: keep Agent module contract-stable and runtime-usable, but implement only a minimal execution surface in phase 1.

### 14.1 MVP Agent Scope

Implement two built-in agent paths:

1. `ChatAgent` (single-call baseline)
- one OpenAI-compatible model generation from task input
- no tool loop
- strongest baseline for early validation

2. `ReActAgent` (minimal tool-capable loop)
- iterative think/act/observe loop with tool use
- stop condition + max step limit
- unified trace emission

This gives immediate utility while preserving a stable contract for future framework adapters.

### 14.2 Adapter-Ready Agent Contract

Agent interface should already support future adaptation from major frameworks.

Must include:

- normalized `AgentState`
- normalized `Action` and `Observation` records
- deterministic stop reason taxonomy
- trace hooks for each decision/action/result step

### 14.3 Phase Separation

- Phase 1: native agents (`ChatAgent`, `ReActAgent`) only
- Phase 2: adapters for LangGraph/AutoGen/OpenAI Agents SDK
- Phase 3: richer multi-agent orchestration and advanced memory modes

---

## 15. Phase-1 Delivery Principle

MVP is \"small but real\":

- real model calls via OpenAI-compatible interface
- real task/agent/scorer execution path
- real benchmark loading via TaskProvider
- real user-facing CLI/TUI quality

Avoid broad but shallow integrations in phase 1.

---

## 16. Example Layout Convention

To keep onboarding friction low and examples easy to run, Snowl adopts a fixed example layout from now on.

- All runnable examples live in top-level `examples/` (sibling of `snowl/`, not `snowl/examples`).
- Each example must use its own folder.
- Each example folder should include:
  - `agent.py`
  - `task.py`
  - `scorer.py`
  - optional `tool.py`
  - optional `README.md` with run command and notes

Recommended run path:

```bash
snowl eval examples/<example_name>
```
