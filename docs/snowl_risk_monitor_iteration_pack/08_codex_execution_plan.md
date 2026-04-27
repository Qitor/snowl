# Codex Execution Plan

This file is meant to be handed directly to Codex.

## Branching plan

Use one PR or branch per package:

1. `benchmark-taxonomy-contract`
2. `artifact-schema-v2-and-finalize-convergence`
3. `model-metadata-and-filters`
4. `p0-benchmark-pack`
5. `risk-monitor-backend-api`
6. `frontend-split-risk-vs-runs`
7. `docs-and-tests-sync`

## Execution rules

- preserve backward compatibility where possible
- keep operator workflows intact
- prefer additive changes over breaking rewrites
- do not redesign scheduler or provider stack in this iteration
- update docs and tests in the same PR when contract changes
- maintain `CHANGELOG.md` and add a README news entry for visible milestones

## Per-package checklist format

For every package:
- implement code changes
- add tests
- update docs
- run targeted validation
- write a short migration note if contracts changed

## Suggested validation commands

```bash
pytest tests/test_benchmark_registry_and_cli.py
pytest tests/test_benchmark_metadata_contract.py
pytest tests/test_aggregator_summary.py
pytest tests/test_eval_artifact_schema.py
pytest tests/test_runtime_engine.py
pytest tests/test_risk_rollups.py
pytest tests/test_project_model_matrix.py
pytest tests/test_project_model_metadata.py
pytest tests/test_web_monitor_store.py
pytest tests/test_eval_web_observability.py
pytest tests/test_monitor_leaderboards.py
pytest tests/test_examples_lint_and_p1_matrix.py
```

## Package-specific completion signal

### 1. benchmark-taxonomy-contract
Done when benchmark listing can drive frontend and backend filtering without hardcoded benchmark-domain logic.

### 2. artifact-schema-v2-and-finalize-convergence
Done when completed runs always emit dashboard-native rollups.

### 3. model-metadata-and-filters
Done when risk views can facet by company/country/source type/reasoning.

### 4. p0-benchmark-pack
Done when WMDP-Cyber, WMDP-Chem, StrongReject, and MASK are all visible in benchmark list and produce stable rollups.

### 5. risk-monitor-backend-api
Done when homepage data can load from domain/benchmark endpoints.

### 6. frontend-split-risk-vs-runs
Done when `/` is risk dashboard and `/runs` remains operator workspace.

### 7. docs-and-tests-sync
Done when docs, examples, and tests all match the new architecture.

## Things Codex should not spend time on in this round

- distributed execution
- provider abstraction overhaul
- complete phase-aware scheduler refactor
- environment-heavy benchmark integrations unless explicitly included
