# Snowl Phase-1 (P0) Outcome Review

Date: 2026-03-02

## 1) Final Verdict

P0 is complete.

Exit criteria in `task_p0.md` are satisfied:

1. `snowl eval .` runs end-to-end with `task.py + agent.py + scorer.py`.
2. `snowl bench run <benchmark_name> --agent agent.py --scorer scorer.py` path is supported via benchmark adapters and runtime integration.
3. Runtime supports task-level sandbox specs, spec-hash reuse (warm pool), and retry-related reliability (resume/rerun-failed + model transient retry).
4. CLI/TUI provides live progress, failures, compare view, and interaction controls.

## 2) What Was Delivered

- Core contracts: `Task`, `TaskProvider`, `Agent`, `Scorer`, `TaskResult` (+ validation and serialization).
- Built-in agents: `ChatAgent`, `ReActAgent` (tool-aware loop).
- Tool system: `ToolSpec` interface, `@tool` decorator, signature/docstring parsing, registry auto-discovery from `tool.py`.
- Env/sandbox: ops contracts, `SandboxSpec` normalization/hash, two-phase runtime, warm pool by `spec_hash`.
- Runtime engine: trial execution, status taxonomy, limits, scoring pipeline, checkpoint/resume, rerun-failed-only.
- UX/CLI: auto-discovery eval flow, plan/global/trial/compare/summary rendering, control hints, stable rendering for narrow width + concurrent updates.
- Benchmark ecosystem: registry, `bench list/run/check`, JSONL + CSV adapters, conformance checks.
- Artifacts/report: plan/summary/outcomes/aggregate/manifest, diagnostics bundle/index, HTML report.

## 3) Step 8 Completion (I-001 ~ I-005)

- I-001: Core contract unit coverage and validation/error-path tests added.
- I-002: Local 3-file integration regression snapshot test added.
- I-003: Benchmark TaskProvider integration test added (deterministic IDs + manifest/rerun command checks).
- I-004: Failure-path tests added (tool error, sandbox runtime failure, retry recovery).
- I-005: TUI snapshot/stability tests added (golden screens, narrow terminal truncation, concurrent rendering structure).

## 4) Reliability Evidence

- Test suite result: `67 passed`.
- CI workflow added: `.github/workflows/ci.yml` (runs on `push` and `pull_request`).

## 5) P1 Recommendations

- Expand real environment adapters in `envs/` (container backends, remote sandboxes, richer ops).
- Upgrade report visuals from baseline tables to stronger charting.
- Add richer agent adapter ecosystem beyond native `ChatAgent`/`ReActAgent`.
