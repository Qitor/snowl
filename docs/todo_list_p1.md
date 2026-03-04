# Snowl P1 TODO List (Issue-Level)

This file expands `task_p1.md` into executable tasks.

## Usage

- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- Priority values: `P0`, `P1`, `P2`
- P1 global principle: semantic alignment first (task loading + scorer rules), not full upstream fidelity.

---

## Reference File Index (Must Use During Implementation)

All paths below are absolute and must be treated as primary references for P1 implementation.

### OSWorld (task loading + env + official agent)
- `/Users/morinop/coding/snowl_v2/references/OSWorld/run.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/lib_run_single.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/test_all.json`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/examples/`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/desktop_env.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/actions.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/controllers/python.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/providers/docker/provider.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/evaluators/getters/`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/evaluators/metrics/`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/qwen3vl_agent.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/utils/qwen_vl_utils.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/prompts.py`

### terminalbench (task loading + terminal env + official agent)
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/CLAUDE.md`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/harness/harness.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/harness/models.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/dataset/dataset.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/handlers/trial_handler.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/terminal.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/tmux_session.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/docker_compose_manager.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/terminus_1.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/prompt-templates/terminus.txt`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/prompt-templates/timeout.txt`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/parsers/base_parser.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/parsers/pytest_parser.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/cli/template-task/task.yaml`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/cli/template-task/run-tests.sh`

### strongreject (task loading + scorer + judge rubric)
- `/Users/morinop/coding/snowl_v2/references/strongreject/README.md`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/simple_jailbreak_runner.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator_prompt.txt`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/AIM.txt`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject_dataset/strongreject_dataset.csv`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject_dataset/strongreject_small_dataset.csv`

---

## A. Shared Scorer Library

ID: P1-A-001
Title: Create `snowl/scorer/` package and base scorer interfaces
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- New scorer package with public exports.
- Common scorer utility types and error taxonomy added.
- Basic docs and unit tests exist.

ID: P1-A-002
Title: Implement `includes()` scorer primitive
Priority: P0
Status: DONE
Depends on: P1-A-001
Definition of done:
- Checks target appears in model output.
- Supports case-sensitive/insensitive option.
- Unit tests cover positive/negative/edge cases.

ID: P1-A-003
Title: Implement `match()` scorer primitive
Priority: P0
Status: DONE
Depends on: P1-A-001
Definition of done:
- Supports matching at start/end.
- Supports ignore-case/whitespace/punctuation controls.
- Unit tests cover all options.

ID: P1-A-004
Title: Implement `pattern()` scorer primitive
Priority: P0
Status: DONE
Depends on: P1-A-001
Definition of done:
- Regex extraction with group selection and flags.
- Predictable behavior on no-match and invalid regex.
- Unit tests cover extraction and failure paths.

ID: P1-A-005
Title: Implement `model_as_judge_json()` scorer
Priority: P0
Status: DONE
Depends on: P1-A-001
Definition of done:
- API: `model_as_judge_json(model_name, system_prompt, schema=None)`.
- Enforces JSON output with schema validation.
- Stores judge input/output/parsed artifacts for traceability.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator_prompt.txt`

ID: P1-A-006
Title: Implement scorer composition (weighted and chained)
Priority: P1
Status: DONE
Depends on: P1-A-002, P1-A-003, P1-A-004, P1-A-005
Definition of done:
- Weighted composite scorer supported.
- Multi-scorer chain with namespaced metrics.
- Partial failures preserve unaffected metrics.

---

## B. StrongReject Vertical Slice

ID: P1-B-001
Title: Add `snowl/benchmarks/strongreject/` adapter skeleton
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- Adapter registered in benchmark registry.
- Can list splits and load deterministic task IDs.
- No dependency on strongreject package runtime.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/strongreject/README.md`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject_dataset/strongreject_dataset.csv`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject_dataset/strongreject_small_dataset.csv`

ID: P1-B-002
Title: Port StrongReject task loading semantics
Priority: P0
Status: DONE
Depends on: P1-B-001
Definition of done:
- Maps forbidden prompts and metadata into Snowl Task samples.
- Split/filter/limit behavior aligns with benchmark intent.
- Deterministic ID tests pass.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/simple_jailbreak_runner.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject_dataset/strongreject_dataset.csv`

ID: P1-B-003
Title: Implement StrongReject scorer via shared scorer library
Priority: P0
Status: DONE
Depends on: P1-A-005, P1-B-002
Definition of done:
- Judge-based scoring pipeline implemented.
- Parse failure taxonomy and fallback behavior defined.
- Integration tests verify score output schema.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/strongreject_evaluator_prompt.txt`

ID: P1-B-004
Title: Add `examples/strongreject-official/`
Priority: P0
Status: DONE
Depends on: P1-B-003
Definition of done:
- Includes `task.py`, `agent.py`, `scorer.py`, `README.md`.
- Runs via `snowl eval examples/strongreject-official`.
- Example output validates against expected artifacts.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/simple_jailbreak_runner.py`
- `/Users/morinop/coding/snowl_v2/references/strongreject/strongreject/AIM.txt`

---

## C. TerminalBench Vertical Slice

ID: P1-C-001
Title: Add `snowl/benchmarks/terminalbench/` adapter skeleton
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- Adapter registered in benchmark registry.
- Split/list/load behavior available with deterministic IDs.
- No dependency on terminal-bench package runtime.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/dataset/dataset.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/handlers/trial_handler.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/cli/template-task/task.yaml`

ID: P1-C-002
Title: Implement terminalbench task schema mapping
Priority: P0
Status: DONE
Depends on: P1-C-001
Definition of done:
- Instruction/task metadata mapped to Snowl samples.
- Episode/time/task identity mapping is stable.
- Conformance tests cover split/filter/limit behavior.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/handlers/trial_handler.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/harness/models.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/parsers/base_parser.py`

ID: P1-C-003
Title: Implement terminal env contract in `snowl/envs/`
Priority: P0
Status: IN_PROGRESS
Depends on: P1-C-002
Definition of done:
- Terminal operation interface supports command send/wait/capture.
- Env diagnostics output is attached to trace/artifacts.
- Real docker compose container lifecycle works end-to-end for terminalbench tasks.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/terminal.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/tmux_session.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/docker_compose_manager.py`

ID: P1-C-004
Title: Add terminal built-in tools in `snowl/tools/`
Priority: P0
Status: IN_PROGRESS
Depends on: P1-C-003
Definition of done:
- Required tools for Terminus-like loop are available.
- Tool specs declare required ops correctly.
- Tool invocation tests cover timeout and error handling.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/terminus_1.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/terminal/tmux_session.py`

ID: P1-C-005
Title: Implement terminalbench scorer
Priority: P0
Status: IN_PROGRESS
Depends on: P1-C-002, P1-A-001
Definition of done:
- Pass/fail and auxiliary metrics are exposed in Score map.
- Scorer traces contain scorer evidence metadata.
- Integration tests validate expected terminalbench outputs.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/parsers/pytest_parser.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/parsers/base_parser.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/harness/models.py`

ID: P1-C-006
Title: Add `examples/terminalbench-official/`
Priority: P0
Status: IN_PROGRESS
Depends on: P1-C-004, P1-C-005
Definition of done:
- Includes `task.py`, `agent.py`, `scorer.py`, optional `tool.py`, `README.md`.
- Agent behavior follows Terminus-style command batch loop semantics on real containerized terminal.
- Example runnable with `snowl eval` and can execute task-provided tests in container.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/terminus_1.py`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/prompt-templates/terminus.txt`
- `/Users/morinop/coding/snowl_v2/references/terminal-bench/terminal_bench/agents/prompt-templates/timeout.txt`

---

## D. OSWorld Vertical Slice

ID: P1-D-001
Title: Add `snowl/benchmarks/osworld/` adapter skeleton
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- Adapter registered and loadable from CLI.
- Domain/example mapping to deterministic IDs implemented.
- No dependency on OSWorld package runtime.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/test_all.json`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/examples/`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/run.py`

ID: P1-D-002
Title: Implement OSWorld task schema mapping
Priority: P0
Status: DONE
Depends on: P1-D-001
Definition of done:
- Instruction + multimodal observation config mapped into samples.
- Action-space and max-step metadata represented in task/env specs.
- Conformance tests cover split/filter/limit and IDs.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/lib_run_single.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/test_all.json`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/evaluation_examples/examples/`

ID: P1-D-003
Title: Implement GUI env contract in `snowl/envs/`
Priority: P0
Status: DONE
Depends on: P1-D-002
Definition of done:
- GUI env interface supports screenshot/a11y capture and action execution.
- Real container/VM lifecycle diagnostics captured.
- End-to-end task execution runs with real environment lifecycle (not mock-only).
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/desktop_env.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/controllers/python.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/providers/docker/provider.py`

ID: P1-D-004
Title: Add GUI built-in tools in `snowl/tools/`
Priority: P0
Status: DONE
Depends on: P1-D-003
Definition of done:
- click/type/key/scroll/wait/terminate tool set available.
- Tool specs and required ops are consistent with GUI env.
- Tool integration tests pass.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/actions.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/qwen3vl_agent.py`

ID: P1-D-005
Title: Implement OSWorld scorer
Priority: P0
Status: DONE
Depends on: P1-D-002, P1-A-001
Definition of done:
- Benchmark-compatible scoring semantics are encoded.
- Scorer outputs deterministic metrics for fixed fixtures.
- Integration tests validate output schema and traces.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/desktop_env.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/evaluators/getters/`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/desktop_env/evaluators/metrics/`

ID: P1-D-006
Title: Add `examples/osworld-official/`
Priority: P0
Status: DONE
Depends on: P1-D-004, P1-D-005
Definition of done:
- Includes `task.py`, `agent.py`, `scorer.py`, optional `tool.py`, `README.md`.
- Agent behavior follows Qwen3VL-style action loop semantics with real environment execution path.
- Example runnable with `snowl eval` against real containerized setup.
- Reference files:
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/qwen3vl_agent.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/utils/qwen_vl_utils.py`
- `/Users/morinop/coding/snowl_v2/references/OSWorld/mm_agents/prompts.py`

---

## E. Runtime and Reliability Support

ID: P1-E-001
Title: Add bounded concurrency controls for benchmark runs
Priority: P1
Status: DONE
Depends on: none
Definition of done:
- `max_trials`, `max_sandboxes`, `max_builds`, `max_model_calls` controls available.
- Scheduler/backpressure behavior documented and tested.
- No unbounded growth in active execution units.

ID: P1-E-002
Title: Improve checkpoint/resume for long-running benchmark jobs
Priority: P1
Status: DONE
Depends on: P1-E-001
Definition of done:
- Checkpoint granularity supports partial benchmark progress recovery.
- Resume correctness tests pass under injected failures.
- Rerun-failed flow remains deterministic.

ID: P1-E-003
Title: Add benchmark-scale diagnostics and profiling hooks
Priority: P1
Status: DONE
Depends on: P1-E-001
Definition of done:
- Runtime emits benchmark-phase timing and failure diagnostics.
- Throughput baseline script/reports added for terminalbench and osworld fixtures.
- Regression tests guard major runtime slowdowns.

ID: P1-E-004
Title: Persist full eval run log (`.log`) for every run
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- Every `snowl eval` / `snowl bench run` writes a complete run log file under artifacts.
- Log includes runtime phases, trial-level status, tool/scorer/sandbox errors, and summary.
- Log path is printed in CLI summary and validated by tests.

---

## F. UX, Examples, and Quality Gates

ID: P1-F-001
Title: Enforce top-level `examples/` structure checks
Priority: P0
Status: DONE
Depends on: none
Definition of done:
- Validation/lint checks ensure example folders follow required files.
- CI runs these checks.
- Error messages are actionable.

ID: P1-F-002
Title: Add benchmark conformance extensions
Priority: P0
Status: DONE
Depends on: P1-B-001, P1-C-001, P1-D-001
Definition of done:
- `snowl bench check` includes semantic checks for task loading and score schema.
- Reports benchmark-specific compatibility hints.
- Conformance tests added for all three target benchmarks.

ID: P1-F-003
Title: Add P1 integration test matrix
Priority: P0
Status: DONE
Depends on: P1-B-004, P1-C-006, P1-D-006
Definition of done:
- CI covers `eval` and `bench run` smoke paths for three benchmark slices.
- Artifact schema and scorer outputs validated in integration tests.
- Failures provide clear phase-level diagnostics.

---

## G. AgentVariant First-Class UX (Final P1 Stage)

ID: P1-G-001
Title: Define `AgentVariant` schema and validation contracts
Priority: P0
Status: DONE
Depends on: P1-F-003
Definition of done:
- New schema supports `agent_id`, `variant_id`, `model`, `params`, optional provenance.
- Validation errors are actionable and strict for identity fields.
- Backward compatibility path exists for single-agent exports.

ID: P1-G-002
Title: Make runtime trial identity and artifacts variant-aware
Priority: P0
Status: DONE
Depends on: P1-G-001
Definition of done:
- Trial identity includes `variant_id` deterministically.
- Checkpoint/resume/rerun-failed semantics remain correct with variant matrices.
- Artifacts expose variant metadata in per-trial and aggregate outputs.

ID: P1-G-003
Title: Add first-class variant discovery/expansion in eval planning
Priority: P0
Status: DONE
Depends on: P1-G-001
Definition of done:
- `agent.py` can export variant collections directly.
- Same scaffold + multiple models expands into stable variant sets.
- Planning output clearly shows `Task x AgentVariant x Sample` dimensions.

ID: P1-G-004
Title: Add variant CLI UX (`--variant` + compare ergonomics)
Priority: P1
Status: DONE
Depends on: P1-G-003
Definition of done:
- CLI supports selecting/filtering variants explicitly.
- Combined filters across `--task`, `--agent`, `--variant` behave predictably.
- Help/docs include practical comparison recipes.

ID: P1-G-005
Title: Add variant-aware TUI/report compare views
Priority: P1
Status: DONE
Depends on: P1-G-003
Definition of done:
- TUI and HTML/JSON reports can group by agent/variant/model.
- Sort order and labels are stable and human-readable.
- Compare output highlights per-variant score deltas clearly.

ID: P1-G-006
Title: Add reliability and scale guards for large variant sweeps
Priority: P1
Status: DONE
Depends on: P1-G-002, P1-G-003
Definition of done:
- Bounded fan-out and failure isolation for many variants.
- Diagnostics identify failing variant quickly.
- Integration tests cover high-cardinality variant runs.

---

## H. Advanced Live CLI (Claude Code-like) (Final P1 Stage)

ID: P1-H-001
Title: Implement multi-panel live dashboard renderer
Priority: P0
Status: DONE
Depends on: P1-G-003
Definition of done:
- Terminal UI includes global progress, active trials, event stream, compare panel, and failure panel.
- Layout remains stable under dynamic updates.
- Falls back gracefully on narrow terminals.

ID: P1-H-002
Title: Add interactive control loop and command palette
Priority: P0
Status: DONE
Depends on: P1-H-001
Definition of done:
- Supports pause/resume, rerun failed, failed-only focus, and task/agent/variant filters.
- Key mappings are discoverable from in-UI help.
- Interactions are reflected immediately with clear confirmations.

ID: P1-H-003
Title: Stream trace/tool/scorer/sandbox events in real time
Priority: P0
Status: DONE
Depends on: P1-H-001
Definition of done:
- Event stream shows incremental trial lifecycle updates with phase tags.
- Judge/scorer and sandbox diagnostics are visible during run.
- Noise controls allow compact and verbose modes.

ID: P1-H-004
Title: Build in-session variant compare board
Priority: P1
Status: DONE
Depends on: P1-G-005, P1-H-001
Definition of done:
- Compare board groups by task/agent/variant/model.
- Displays score deltas and rank changes during execution.
- Supports sort toggles and stable ordering.

ID: P1-H-005
Title: Guarantee no-ui parity for live interactions
Priority: P1
Status: DONE
Depends on: P1-H-002
Definition of done:
- Each interactive action has deterministic CLI/no-ui equivalent.
- Re-run commands and filter state are reproducible from artifacts.
- Parity tests validate interactive vs scripted outcomes.

ID: P1-H-006
Title: Add UI reliability and performance guards
Priority: P1
Status: DONE
Depends on: P1-H-001, P1-H-003
Definition of done:
- UI refresh is throttled and buffer sizes are bounded.
- No runaway memory growth on long benchmark runs.
- Stress tests cover high-frequency event bursts.

ID: P1-H-007
Title: Add Live CLI showcase demos and snapshot tests
Priority: P1
Status: DONE
Depends on: P1-H-002, P1-H-004
Definition of done:
- Snapshot tests lock key screens and transitions.
- A one-command demo flow is documented for project presentation.
- Demo covers pause/filter/compare/rerun interactions.

ID: P1-H-008
Title: Show container startup/config process in Live CLI
Priority: P0
Status: DONE
Depends on: P1-H-001, P1-E-003
Definition of done:
- Live UI displays container build/pull/start stages with timestamps.
- Shows effective container config snapshot (image, compose file, env highlights, resources).
- Startup failures are surfaced with actionable diagnostics in-session.

---

## I. Decorator-Based Authoring (`@task/@agent/@scorer`)

ID: P1-I-001
Title: Add `@task`, `@agent`, `@scorer` decorators in core API
Priority: P0
Status: DONE
Depends on: P1-F-003
Definition of done:
- Core exports `@task`, `@agent`, `@scorer` with metadata attachment.
- Decorators support explicit id assignment and metadata options.
- Backward compatibility with existing class/object style remains.

ID: P1-I-002
Title: Make autodiscovery decorator-first with safe fallback
Priority: P0
Status: DONE
Depends on: P1-I-001
Definition of done:
- Eval discovery prioritizes decorated objects first.
- Fallback protocol-based discovery still works for old examples.
- Deterministic precedence and conflict handling are documented and tested.

ID: P1-I-003
Title: Add id/ambiguity validation for mixed declaration modes
Priority: P1
Status: DONE
Depends on: P1-I-002
Definition of done:
- Duplicate ids across decorated/non-decorated objects fail with actionable errors.
- Missing ids in strict mode fail with clear guidance.
- Mixed-mode ambiguity is detected and explained.

ID: P1-I-004
Title: Migrate official examples to decorator style
Priority: P1
Status: DONE
Depends on: P1-I-002
Definition of done:
- `examples/*-official` use decorator style for task/agent/scorer where applicable.
- Wrapper boilerplate is removed unless needed for real runtime logic.
- Example docs reflect new recommended pattern.

---

## J. Suggested Execution Order

Step 1:
- P1-A-001, P1-A-002, P1-A-003, P1-A-004, P1-A-005

Step 2:
- P1-B-001, P1-B-002, P1-B-003, P1-B-004

Step 3:
- P1-C-001, P1-C-002, P1-C-003, P1-C-004, P1-C-005, P1-C-006

Step 4:
- P1-D-001, P1-D-002, P1-D-003, P1-D-004, P1-D-005, P1-D-006

Step 5:
- P1-E-001, P1-E-002, P1-E-003, P1-E-004, P1-A-006

Step 6:
- P1-F-001, P1-F-002, P1-F-003

Step 7:
- P1-G-001, P1-G-002, P1-G-003, P1-G-004, P1-G-005, P1-G-006

Step 8:
- P1-I-001, P1-I-002, P1-I-003, P1-I-004

Step 9:
- P1-H-001, P1-H-002, P1-H-003, P1-H-004, P1-H-005, P1-H-006, P1-H-007, P1-H-008

---

## K. P1 Cut Line

Must-have for P1:
- P1-A-001..P1-A-005
- P1-B-001..P1-B-004
- P1-C-001..P1-C-006
- P1-D-001..P1-D-006
- P1-F-001..P1-F-003
- P1-G-001..P1-G-006
- P1-I-001..P1-I-004
- P1-H-001..P1-H-008
- P1-E-004

Can follow after first P1 release:
- P1-A-006
- P1-E-001..P1-E-003

---

## L. P1.5 / P2 Backlog (Agent Framework Adapters)

The items below are intentionally NOT in current P1 critical path.

ID: P2-I-001
Title: LangChain adapter
Priority: P2
Status: TODO
Depends on: P1-A-001, P1-F-003
Definition of done:
- LangChain agent wrapper can run through `snowl eval`.
- Tool and trace normalization mapped to Snowl contracts.
- Adapter compatibility tests and example added.

ID: P2-I-002
Title: OpenAI Agents SDK adapter
Priority: P2
Status: TODO
Depends on: P1-A-001, P1-F-003
Definition of done:
- OpenAI Agents SDK wrapper can run through `snowl eval`.
- Agent state/actions/observations mapped into Snowl trace schema.
- Adapter compatibility tests and example added.

ID: P2-I-003
Title: Adapter plugin registry for third-party frameworks
Priority: P2
Status: TODO
Depends on: P2-I-001, P2-I-002
Definition of done:
- Framework adapters discoverable via plugin registry.
- Adapter capability declarations and validation checks implemented.
- User docs include adapter authoring guide.
