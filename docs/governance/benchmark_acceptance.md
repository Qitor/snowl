# Benchmark Acceptance Policy

## General rule

New third-party benchmark integrations should normally live **outside** the main `snowl` repository, in the planned `snowl-evals` collection or as standalone packages.

## What may be accepted into `snowl`

The main repository may accept only:

- **Tiny reference adapters** — minimal examples demonstrating the adapter contract
- **Generic data adapters** — CSV, JSONL, and other format-driven adapters
- **Conformance fixtures** — test fixtures used by the conformance utility
- **Minimal examples** — needed to test framework behavior itself

## Benchmark integration requirements

A benchmark integration (whether in `snowl-evals` or standalone) requires:

1. **Manifest** — a `benchmark.yaml` following the `snowl.benchmark_manifest.v1` schema
2. **Source attribution** — paper URL, code URL, dataset URL
3. **License notes** — license of the original dataset and any derived materials
4. **Dependency declaration** — optional extras in `pyproject.toml`, no hard dependencies
5. **Scoring documentation** — method, metric names, interpretation guidelines
6. **Sample fixture** — at least one small fixture for conformance testing
7. **Conformance test** — passes `snowl.benchmarks.conformance` checks
8. **Reproducibility notes** — deterministic? seed-supported? known caveats?

## Review criteria

When reviewing a benchmark integration PR, maintainers should check:

- Does the adapter follow `BaseBenchmarkAdapter` or `BenchmarkAdapter` protocol?
- Is benchmark-specific logic confined to the adapter package?
- Are heavy dependencies optional?
- Is the manifest complete and valid?
- Does the conformance test pass?
- Is the scoring method clearly documented?
- Are there no imports from the benchmark package into core/runtime/tools?

## Exceptions

Existing built-in benchmarks (AgentDojo, ToolEmu, etc.) remain in `snowl` until the `snowl-evals` migration is complete. New benchmarks should not be added to `snowl/benchmarks/` without explicit maintainer approval.
