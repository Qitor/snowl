# Snowl MVP TODO List (Issue-Level)

This file expands `task_p0.md` into executable TODO items for Phase-1.

## Usage

- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- Priority values: `P0`, `P1`, `P2`
- Keep tasks small enough to finish in 0.5-2 days.

---

## A. Foundation and Contracts

ID: A-001
Title: Define `Task` protocol and schema validation
Priority: P0
Status: TODO
Depends on: none
Definition of done:
- `Task` protocol is implemented with required fields: `task_id`, `env_spec`, sample iterator.
- Invalid task definitions fail fast with actionable error messages.
- Unit tests cover valid and invalid schema cases.

ID: A-002
Title: Define `TaskProvider` protocol for benchmark loading
Priority: P0
Status: TODO
Depends on: A-001
Definition of done:
- Protocol methods exist: `list_splits`, `count`, `iter_tasks`, `get_task`.
- Protocol docs include lazy iteration requirements.
- Unit tests validate deterministic task IDs and split behavior.

ID: A-003
Title: Define `Agent` protocol and normalized runtime types
Priority: P0
Status: TODO
Depends on: none
Definition of done:
- `Agent` protocol includes normalized run/step lifecycle.
- `AgentState`, `Action`, `Observation`, `StopReason` are implemented.
- Agent runtime type docs include future adapter requirements.

ID: A-004
Title: Define `Scorer` protocol with multi-metric output
Priority: P0
Status: TODO
Depends on: A-001
Definition of done:
- Scorer input contract: `TaskResult + Trace + Context`.
- Scorer output contract: `dict[str, Score]`.
- Validation and examples for multi-metric scoring are documented.

ID: A-005
Title: Implement stable `TaskResult` core schema + `payload`
Priority: P0
Status: TODO
Depends on: A-001, A-003, A-004
Definition of done:
- Core fields implemented: IDs, status, timing, usage, output, error, artifacts.
- Extensible `payload` supported.
- JSON serialization is stable and tested.

ID: A-006
Title: Define run identity and manifest schema
Priority: P0
Status: TODO
Depends on: A-005
Definition of done:
- Run manifest includes dataset fingerprint, task/agent/scorer version, model version, seed/epoch, spec hash.
- Schema versioning strategy documented.
- Roundtrip tests for manifest read/write pass.

---

## B. Model Module (OpenAI-Compatible)

ID: B-001
Title: Implement OpenAI-compatible chat client wrapper
Priority: P0
Status: TODO
Depends on: A-005
Definition of done:
- Supports `base_url`, `api_key`, `model`.
- Supports timeout and retry configuration.
- Returns normalized output and usage metadata.

ID: B-002
Title: Add model config loading from CLI and env
Priority: P0
Status: TODO
Depends on: B-001
Definition of done:
- Reads `OPENAI_API_KEY` and custom base URL env vars.
- CLI overrides env values predictably.
- Startup validation emits clear errors for missing config.

ID: B-003
Title: Normalize model errors into runtime error taxonomy
Priority: P1
Status: TODO
Depends on: B-001
Definition of done:
- Transient vs terminal errors are distinguishable.
- Retry logic consumes normalized error classes.
- Error snapshots are attached to `TaskResult`.

---

## C. Agent Module MVP

ID: C-001
Title: Implement `ChatAgent` baseline
Priority: P0
Status: TODO
Depends on: A-003, B-001
Definition of done:
- Single OpenAI-compatible generation call agent runs end-to-end.
- Emits normalized trace events.
- Produces scoreable `TaskResult`.

ID: C-002
Title: Implement `ReActAgent` minimal iterative runner
Priority: P0
Status: TODO
Depends on: C-001
Definition of done:
- ReAct loop supports think/act/observe transitions.
- Supports `max_steps` and deterministic stop reasons.
- Loop traces include step-level timing and outcomes.

ID: C-003
Title: Add tool invocation runtime contract
Priority: P0
Status: TODO
Depends on: A-003
Definition of done:
- Tool call interface supports sync and async execution.
- Tool failures are structured and traceable.
- Tool outputs are bounded and serializable.

ID: C-004
Title: Add tool-env ops compatibility enforcement
Priority: P0
Status: TODO
Depends on: C-003, D-001
Definition of done:
- Runtime validates `required_ops <= provided_ops` before execution.
- Validation errors are explicit and non-ambiguous.
- Tests cover allow and reject paths.

ID: C-005
Title: Prepare agent adapter registry interface (no adapters yet)
Priority: P1
Status: TODO
Depends on: A-003
Definition of done:
- Plugin entrypoint interface is defined.
- Native agents and future adapters share same contract.
- Contract doc includes migration guidance for framework adapters.

---

## D. Environment and Sandbox Runtime

ID: D-001
Title: Define Ops interfaces (`FileOps`, `ProcessOps`, `WebOps`)
Priority: P0
Status: TODO
Depends on: A-001
Definition of done:
- Ops interfaces are versioned and documented.
- Environment implementations expose `provided_ops`.
- Contract tests validate capability declaration.

ID: D-002
Title: Implement normalized `SandboxSpec`
Priority: P0
Status: TODO
Depends on: D-001
Definition of done:
- Spec supports build/image/resources/network basics.
- Normalization produces deterministic canonical form.
- Validation catches invalid combinations.

ID: D-003
Title: Implement `spec_hash` dedup for sandbox setup
Priority: P0
Status: TODO
Depends on: D-002
Definition of done:
- Same spec yields same hash across runs.
- Different meaningful spec changes yield different hashes.
- Hash is attached to trial metadata.

ID: D-004
Title: Implement two-phase sandbox lifecycle (`prepare`, `run`)
Priority: P0
Status: TODO
Depends on: D-002
Definition of done:
- `prepare` handles build/pull/setup.
- `run` handles start/exec/teardown.
- Failures in either phase are captured with diagnostics.

ID: D-005
Title: Implement minimal warm pool keyed by `spec_hash`
Priority: P1
Status: TODO
Depends on: D-003, D-004
Definition of done:
- Reuse policy for same hash is functional.
- Pool limits and eviction strategy are configurable.
- Reuse metrics are exposed in runtime stats.

ID: D-006
Title: Add sandbox failure diagnostics bundle
Priority: P1
Status: TODO
Depends on: D-004
Definition of done:
- Capture container/session id, startup latency, teardown reason.
- Persist diagnostics in artifacts per trial.
- Failures are visible in CLI/TUI summary.

---

## E. Runtime Engine, Limits, Resume

ID: E-001
Title: Implement trial execution engine for `Task x AgentVariant x Sample`
Priority: P0
Status: TODO
Depends on: A-005, C-001, C-002, B-001
Definition of done:
- Engine executes complete trial lifecycle.
- Trial identity is deterministic.
- Score pipeline can consume engine outputs.

ID: E-002
Title: Implement status taxonomy and transitions
Priority: P0
Status: TODO
Depends on: E-001
Definition of done:
- Statuses: `success`, `incorrect`, `limit_exceeded`, `error`, `cancelled`.
- Transition table documented and enforced.
- No unclassified terminal states remain.

ID: E-003
Title: Implement core limits (`max_steps`, `time_limit`, `token_limit`)
Priority: P0
Status: TODO
Depends on: E-001
Definition of done:
- Limits stop execution safely.
- Limit exits produce scoreable results.
- Limit reasons visible in trace and summary.

ID: E-004
Title: Implement checkpointing and resume
Priority: P0
Status: TODO
Depends on: A-006, E-001
Definition of done:
- Interrupted runs can resume from checkpoint.
- Completed trials are not re-executed.
- Resume behavior is deterministic and tested.

ID: E-005
Title: Implement rerun-failed-only mode
Priority: P1
Status: TODO
Depends on: E-004
Definition of done:
- CLI supports rerunning only failed trials.
- Successful trials remain untouched.
- Summary reports differentiate original vs rerun outcomes.

---

## F. CLI, Auto-Discovery, and TUI

ID: F-001
Title: Implement `snowl eval .` auto-discovery
Priority: P0
Status: TODO
Depends on: A-001, A-003, A-004
Definition of done:
- Discovers `task.py`, `agent.py`, `scorer.py`.
- Validates discovery conflicts with clear messages.
- Works for single and multiple definitions.

ID: F-002
Title: Implement auto planning (single/sweep/matrix)
Priority: P0
Status: TODO
Depends on: F-001, E-001
Definition of done:
- Rule-based expansion is deterministic.
- User can constrain with `--task` and `--agent`.
- Plan preview is shown before execution.

ID: F-003
Title: Build TUI global panel
Priority: P0
Status: TODO
Depends on: E-001
Definition of done:
- Displays progress, pass/fail/error, time, token/cost, sandbox health.
- Refresh is stable under concurrent updates.
- Layout degrades gracefully on narrow terminals.

ID: F-004
Title: Build TUI trial panel
Priority: P0
Status: TODO
Depends on: E-001
Definition of done:
- Shows active trials and latest trace snippets.
- Highlights failures and retry state.
- Supports filtering by task/agent/status.

ID: F-005
Title: Build TUI compare panel
Priority: P0
Status: TODO
Depends on: A-004, G-001
Definition of done:
- Live leaderboard for multi-metric scores.
- Supports group-by task, agent, model.
- Ranking logic is stable and documented.

ID: F-006
Title: Implement interactive keyboard controls
Priority: P1
Status: TODO
Depends on: F-003, F-004, F-005
Definition of done:
- Supports pause/resume/filter/group/rerun-failed.
- Key bindings are discoverable in help footer.
- No key action causes terminal corruption.

ID: F-007
Title: End-of-run summary and rerun hint
Priority: P0
Status: TODO
Depends on: E-001, G-001
Definition of done:
- Summary includes key metrics and failure buckets.
- Prints exact reproducible rerun command.
- Saves machine-readable and human-readable artifacts.

---

## G. Aggregation and Reporting

ID: G-001
Title: Implement aggregator baseline for multi-metric outputs
Priority: P0
Status: TODO
Depends on: A-004, A-005, E-001
Definition of done:
- Aggregates by task, agent, model, split.
- Supports matrix comparison output.
- Handles missing/failed samples explicitly.

ID: G-002
Title: Define standard result artifact schemas (JSON/JSONL)
Priority: P0
Status: TODO
Depends on: G-001
Definition of done:
- Schema versioned and documented.
- Artifacts include run manifest reference.
- Compatibility tests protect schema stability.

ID: G-003
Title: Generate basic HTML report
Priority: P1
Status: TODO
Depends on: G-001, G-002
Definition of done:
- Includes summary cards, comparison table, failure breakdown.
- Links to trial diagnostics and traces.
- Opens locally without extra backend service.

---

## H. Benchmark Ecosystem

ID: H-001
Title: Implement benchmark registry
Priority: P0
Status: TODO
Depends on: A-002
Definition of done:
- Registry can list installed benchmark adapters.
- Adapter metadata includes name/version/supported splits.
- Registry API is stable and test-covered.

ID: H-002
Title: Implement `snowl bench list`
Priority: P0
Status: TODO
Depends on: H-001
Definition of done:
- Lists available benchmarks with concise metadata.
- Handles missing adapters gracefully.
- Output can be parsed in plain mode.

ID: H-003
Title: Implement `snowl bench run <name>`
Priority: P0
Status: TODO
Depends on: H-001, E-001, F-002
Definition of done:
- Runs benchmark tasks via TaskProvider path.
- Accepts agent/scorer inputs consistently with `snowl eval`.
- Shares same runtime and result schema.

ID: H-004
Title: Build first benchmark adapter (Adapter #1)
Priority: P0
Status: TODO
Depends on: A-002, H-001
Definition of done:
- Adapter outputs valid Task objects lazily.
- Deterministic task IDs verified.
- End-to-end run succeeds via `snowl bench run`.

ID: H-005
Title: Build second benchmark adapter (Adapter #2)
Priority: P1
Status: TODO
Depends on: H-004
Definition of done:
- Different benchmark schema is mapped successfully.
- Conformance tests pass.
- Adapter docs include usage and caveats.

ID: H-006
Title: Implement adapter conformance test command
Priority: P0
Status: TODO
Depends on: A-002, H-001
Definition of done:
- Verifies required TaskProvider behaviors.
- Verifies schema/ID/split invariants.
- Failing adapters report actionable guidance.

---

## I. Testing and Reliability

ID: I-001
Title: Add unit test suite for core contracts
Priority: P0
Status: TODO
Depends on: A-001, A-003, A-004, A-005
Definition of done:
- Task/Agent/Scorer/TaskResult contracts covered.
- Validation and error cases covered.
- CI runs tests on every push.

ID: I-002
Title: Add integration test for local 3-file flow
Priority: P0
Status: TODO
Depends on: F-001, E-001
Definition of done:
- `task.py + agent.py + scorer.py` path runs in CI.
- Produces expected result artifacts.
- Regression snapshots protect outputs.

ID: I-003
Title: Add integration test for benchmark TaskProvider flow
Priority: P0
Status: TODO
Depends on: H-003, H-004
Definition of done:
- `snowl bench run` path runs in CI.
- Adapter to runtime to scorer path validated.
- Deterministic IDs and manifest references verified.

ID: I-004
Title: Add failure-path tests (timeout/tool/sandbox/retry)
Priority: P0
Status: TODO
Depends on: E-003, D-004, C-003
Definition of done:
- Each failure type is simulated and asserted.
- Runtime returns scoreable terminal states.
- Diagnostics and traces are preserved.

ID: I-005
Title: Add TUI snapshot and rendering stability tests
Priority: P1
Status: TODO
Depends on: F-003, F-004, F-005
Definition of done:
- Golden snapshots for key screens exist.
- Narrow terminal handling is tested.
- Concurrent update rendering glitches are guarded.

---

## J. Suggested Execution Plan (Critical Path)

Step 1:
- A-001, A-003, A-004, A-005

Step 2:
- B-001, B-002, C-001

Step 3:
- C-002, E-001, E-002, E-003

Step 4:
- D-001, D-002, D-003, D-004, C-004

Step 5:
- F-001, F-002, F-003, F-004, F-007

Step 6:
- G-001, G-002, H-001, H-002, H-003, H-004, H-006

Step 7:
- E-004, E-005, D-005, D-006, F-005, F-006, G-003, H-005

Step 8:
- I-001, I-002, I-003, I-004, I-005

---

## K. MVP Cut Line

Must-have for first public MVP:

- A-001..A-006
- B-001..B-002
- C-001..C-004
- D-001..D-004
- E-001..E-004
- F-001..F-004 and F-007
- G-001..G-002
- H-001..H-004 and H-006
- I-001..I-004

Can ship after MVP:

- B-003, C-005, D-005, D-006, E-005, F-005, F-006, G-003, H-005, I-005
