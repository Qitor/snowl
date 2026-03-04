# Snowl Phase-1 Tasks (P0)

Goal: shortest path to a usable MVP with strong UX and real execution.

Scope constraints:

- Core paradigm: `Task + Agent + Scorer`
- Model integration: OpenAI-compatible only
- Benchmark integration: TaskProvider-based loading
- UX: interactive, polished CLI/TUI is in P0

---

## 0. Exit Criteria (MVP Done Definition)

MVP is done when all are true:

1. User can run:
```bash
snowl eval .
```
with `task.py + agent.py + scorer.py` and get valid metrics.

2. User can run at least one third-party benchmark via:
```bash
snowl bench run <benchmark_name> --agent agent.py --scorer scorer.py
```

3. Runtime supports task-specific sandbox specs with basic reuse and retry.

4. CLI/TUI shows live progress, failures, and comparison table in an interactive, readable format.

---

## 1. Core Contracts (Week 1)

### 1.1 Task Schema
- [ ] Define `Task` protocol (id, env_spec, sample iterator)
- [ ] Define `TaskProvider` protocol (split/list/count/iter/get)
- [ ] Add schema validation and clear error messages

### 1.2 Agent Schema
- [ ] Define `Agent` protocol (run/step/stop hooks)
- [ ] Define `AgentState`, `Action`, `Observation`, `StopReason`
- [ ] Add trace hook interface at each decision/action boundary

### 1.3 Scorer Schema
- [ ] Define scorer input contract: `TaskResult + Trace + Context`
- [ ] Define multi-metric output contract: `dict[str, Score]`
- [ ] Add scorer registration/discovery from `scorer.py`

### 1.4 TaskResult Schema
- [ ] Implement fixed core fields (`status`, ids, timing, usage, output, error, artifacts)
- [ ] Implement extensible `payload`
- [ ] Add serialization contract for aggregator/report

---

## 2. Runtime MVP (Week 1-2)

### 2.1 Trial Engine
- [ ] Implement `Task x AgentVariant x Sample` execution loop
- [ ] Add deterministic trial identity (`task_id, agent_id, sample_id, seed, epoch`)
- [ ] Add status taxonomy (`success`, `incorrect`, `limit_exceeded`, `error`, `cancelled`)

### 2.2 Retry and Resume
- [ ] Add trial-level checkpointing
- [ ] Add rerun-failed-only mode
- [ ] Add resumable run manifest

### 2.3 Limits
- [ ] Implement `max_steps`, `time_limit`, `token_limit` (minimum set)
- [ ] Ensure limit exit produces scoreable TaskResult (not runtime crash)

---

## 3. Model Module (OpenAI-Compatible Only) (Week 1)

### 3.1 Model Client
- [ ] Implement OpenAI-compatible chat completion wrapper
- [ ] Support `base_url`, `api_key`, `model`, `timeout`, `max_retries`
- [ ] Normalize usage/timing/error metadata into TaskResult

### 3.2 Config and Secrets
- [ ] Read from CLI + env (`OPENAI_API_KEY`, custom base URL)
- [ ] Validate startup config with actionable errors

---

## 4. Agent Module MVP (Week 1-2)

### 4.1 Built-in Native Agents
- [ ] `ChatAgent`: single-call baseline agent (OpenAI-compatible wrapper)
- [ ] `ReActAgent`: minimal iterative think/act/observe loop with max step and stop checks

### 4.2 Tool Integration Baseline
- [ ] Tool invocation contract (sync/async normalized)
- [ ] Tool error handling with structured traces
- [ ] Tool-to-env ops compatibility check

### 4.3 Future Adapter Readiness (without implementing adapters yet)
- [ ] Keep adapter-facing protocol stable
- [ ] Reserve adapter registry entrypoint and plugin hooks

---

## 5. Env/Sandbox MVP (Week 2)

### 5.1 Env Ops Contracts
- [ ] Define Ops interfaces (`FileOps`, `ProcessOps`, `WebOps` baseline placeholders)
- [ ] Enforce `required_ops <= provided_ops`

### 5.2 SandboxSpec Runtime
- [ ] Implement normalized `SandboxSpec`
- [ ] Implement `spec_hash` for dedup/reuse
- [ ] Implement two-phase lifecycle (`prepare`, `run`)

### 5.3 Pooling and Recovery
- [ ] Add minimal warm pool by `spec_hash`
- [ ] Add cleanup and retry-safe reuse policy
- [ ] Capture container/session diagnostics on failure

---

## 6. UX/CLI/TUI (P0, Week 2-3)

### 6.1 Command UX
- [ ] Keep default path simple: `snowl eval .`
- [ ] Auto-discover `task.py/agent.py/scorer.py`
- [ ] Auto-expand plan (single/sweep/matrix)

### 6.2 Interactive TUI
- [ ] Global panel: progress, pass/fail/error, cost/time, sandbox status
- [ ] Trial panel: active runs + latest trace lines
- [ ] Compare panel: live metric leaderboard
- [ ] Keyboard interactions: filter/group/pause/rerun-failed

### 6.3 Run Summary
- [ ] End-of-run concise terminal report
- [ ] Save machine-readable results + human-readable report artifact
- [ ] Show reproducible rerun command in output

---

## 7. Benchmark Ecosystem (Week 2-3)

### 7.1 Registry and CLI
- [ ] Implement benchmark registry
- [ ] `snowl bench list`
- [ ] `snowl bench run <name>`

### 7.2 First Adapters
- [ ] Implement 1-2 benchmark adapters with TaskProvider output
- [ ] Validate adapter output against Task schema

### 7.3 Conformance Checks
- [ ] Add adapter conformance test command
- [ ] Check required split/list/iter behavior
- [ ] Check deterministic task IDs and schema integrity

---

## 8. Aggregation and Reporting (Week 3)

### 8.1 Aggregator Baseline
- [ ] Aggregate multi-metric scorer outputs by task/agent/model
- [ ] Support matrix comparison tables

### 8.2 Output Artifacts
- [ ] Standard JSONL/JSON output schema
- [ ] Basic HTML report (table + key charts)

---

## 9. Quality and Testing (Continuous)

- [ ] Unit tests for all core protocols
- [ ] Integration test: local 3-file eval path
- [ ] Integration test: benchmark -> TaskProvider -> runtime path
- [ ] Failure-path tests: timeout/tool error/sandbox failure/retry
- [ ] Golden snapshot tests for CLI/TUI rendering

---

## 10. Implementation Order (Fastest MVP Path)

1. Core contracts (`Task/Agent/Scorer/TaskResult`)
2. OpenAI-compatible model client
3. Native agents (`ChatAgent`, `ReActAgent`)
4. Runtime loop + scorer + basic outputs
5. Env/sandbox minimal lifecycle with `spec_hash` reuse
6. Auto-discovery CLI (`snowl eval .`)
7. Interactive TUI panels
8. Benchmark registry + first adapter
9. Resume/retry hardening + report polish

---

## 11. Risks and Mitigations

1. Risk: container lifecycle complexity delays MVP
- Mitigation: start with minimal sandbox lifecycle + hash-based reuse, expand incrementally

2. Risk: too many CLI options reduce usability
- Mitigation: keep default command path minimal, hide advanced controls

3. Risk: adapter quality inconsistency
- Mitigation: conformance tests required before registry exposure

4. Risk: unstable agent API due to future framework adaptation
- Mitigation: freeze protocol now; adapters conform later
