# Codex Task Playbook

This file is specifically for future Codex work in Snowl.

## How Codex Should Triage A Task

1. Decide which subsystem owns the behavior.
2. Read the smallest set of docs and files that define that subsystem.
3. Verify current behavior in tests before trusting planning docs.
4. Make the smallest contract-preserving change.
5. Validate with focused tests and, when relevant, artifact inspection.

## If Docs Conflict, Trust In This Order

1. Current code in `snowl/eval.py`, `snowl/runtime/*`, and the owning subsystem.
2. Focused tests that exercise the behavior.
3. `docs/current_state.md` and `docs/runtime_known_gaps.md`.
4. `docs/architecture/runtime_and_scheduler.md`, `docs/testing_and_validation.md`, and `AGENTS.md`.
5. Forward-looking design docs such as `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md`.

## Read First By Task Type

### Runtime Change

Read:

1. `docs/current_state.md`
2. `docs/architecture/runtime_and_scheduler.md`
3. `snowl/eval.py`
4. `snowl/runtime/engine.py`
5. `snowl/runtime/resource_scheduler.py`
6. `tests/test_runtime_engine.py`
7. `tests/test_resource_scheduler.py`
8. `tests/test_eval_web_observability.py`

Do not start here:

- Do not start with `docs/runtime_scheduling*.md` and assume the implementation matches the plan.
- Do not start in `snowl/runtime/resource_scheduler.py` unless you have already confirmed the behavior is actually wired in from `snowl/eval.py`.
- Do not start by extending `TaskExecutionPlan`, `TrialDescriptor`, `begin_prepare()`, or `begin_finalize()` unless the task is explicitly about wiring those into the main eval loop.
- Do not start in a benchmark adapter if the bug is really shared runtime admission, retry, or artifact behavior.

### Benchmark Adapter Change

Read:

1. `docs/project_map.md`
2. `snowl/bench.py`
3. `snowl/benchmarks/registry.py`
4. `snowl/benchmarks/<name>/adapter.py`
5. `snowl/benchmarks/<name>/scorer.py`
6. `tests/test_<name>_benchmark.py`

### Scorer Change

Read:

1. `snowl/core/scorer.py`
2. `snowl/scorer/base.py`
3. `snowl/scorer/model_judge.py` if relevant
4. The benchmark-specific scorer if applicable
5. `tests/test_scorer_contracts.py`

### Docs Change

Read:

1. `AGENTS.md`
2. `docs/project_map.md`
3. `docs/current_state.md`
4. The owning code/tests for the behavior you are documenting

### Debugging Failed Runs

Read:

1. `docs/testing_and_validation.md`
2. `.snowl/runs/<run_id>/manifest.json`
3. `.snowl/runs/<run_id>/runtime_state.json`
4. `.snowl/runs/<run_id>/events.jsonl`
5. `.snowl/runs/<run_id>/profiling.json`
6. `.snowl/runs/<run_id>/run.log`
7. `recovery.json`, `attempts.jsonl`, and `diagnostics/` if retries or benchmark setup are involved

## When Codex Should Propose A Design Doc Before Coding

Propose design first when the task would:

- change runtime scheduling semantics
- change artifact or event schemas
- change monitor/backend contracts used by the UI
- change retry semantics
- change packaging or `webui/` to `snowl/_webui/` mirroring rules
- require a broad runtime rewrite instead of an incremental fix

In Snowl, a short design doc can be:

- a scoped `PLANS.md` update
- a new or updated `docs/architecture/*.md` note

## When Codex Should Update `AGENTS.md`

Update `AGENTS.md` only when the rule is:

- repo-wide
- persistent across tasks
- short enough to stay high-signal

Do not put long architecture walkthroughs in `AGENTS.md`. Put detail in `docs/*.md` and leave `AGENTS.md` as a routing layer.

## When Codex Should Suggest A Reusable Skill

Suggest creating a repo skill under `.agents/skills/` when a workflow is:

- repeated across many tasks
- longer than a short doc reminder
- stable enough to codify
- expensive to relearn from raw files each time

Strong candidates in this repo:

- runtime artifact triage
- benchmark adapter authoring
- web monitor source/mirror sync workflow
- local eval smoke testing and recovery inspection

## Common Traps In This Repo

- `webui/` is the editable source. `snowl/_webui/` is the packaged mirror, not the design source.
- `docs/runtime_scheduling.md` and `docs/runtime_scheduling_v2.md` are design notes, not exact implementation docs.
- `TaskExecutionPlan` and `TrialDescriptor` exist, but the main dispatcher does not yet use them for smarter scheduling.
- `max_container_slots` is not yet a universal gate for every container-backed path.
- `project.yml` supports one provider block today; multi-model support comes from `agent_matrix.models`, not multi-provider scheduling.
- `snowl retry <run_id>` reuses the existing run id and run directory rather than creating a brand-new run.
- The main eval loop currently does not invoke `finalize_trial_phase()`, even though the engine exposes it and `execute_trial()` uses it.
- `references/` contains external repos and local datasets; do not patch them unless the task is explicitly about reference setup.
- Benchmark logic usually belongs in `snowl/benchmarks/<name>/`, not in shared runtime or UI layers.

## Common Misread Patterns

- Seeing an exposed runtime API does not mean the main eval loop uses it.
- Seeing a scheduler budget does not mean every container-backed path is admitted through that budget.
- Seeing a phase helper does not mean that phase is independently scheduled.
- Seeing `spec_hash` in payloads or provider code does not mean the dispatcher is locality-aware.
- Seeing provider admission helpers does not mean dispatch order is provider-aware.

## Practical Prompting For Future Codex Tasks

Good Snowl tasks usually specify:

- goal
- relevant files
- constraints
- exact validation commands
- what must not change

If those are missing, Codex should infer the smallest safe scope and then validate it explicitly.
