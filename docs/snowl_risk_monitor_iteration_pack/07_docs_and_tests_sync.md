# Package 7: Docs and Tests Synchronization

## Goal

Make sure documentation, examples, and tests reflect the new product model so contributors and coding agents do not keep reinforcing the old run-only mental model.

## Directly affected files

- `README.md`
- `README.zh-CN.md`
- `START_HERE.md`
- `docs/project_map.md`
- `docs/current_state.md`
- `PLANS.md`
- `docs/risk_monitor_data_model.md` (new)
- `docs/benchmark_taxonomy.md` (new)
- `docs/benchmark_onboarding_playbook.md` (new)
- `tests/test_examples_lint_and_p1_matrix.py`

## Required documentation changes

### README
Reframe the product in two layers:
- **Operator Layer**
- **Risk Monitor Layer**

### START_HERE
Add a section explaining the full risk-monitor data flow:
- benchmark adapter
- eval outputs
- aggregation
- monitor ingestion
- risk dashboard

### current_state
Update with:
- artifact schema v2
- domain/benchmark rollups
- new benchmark pack status
- homepage split between `/` and `/runs`

### PLANS
Explicitly add a milestone for:
- benchmark taxonomy
- dashboard-native artifacts
- risk monitor APIs
- first risk dashboard homepage

## Required test changes

- add or update examples to include benchmark metadata
- validate example configs with model metadata
- add regression tests for risk rollups and API serialization

## Acceptance criteria

- docs describe current architecture truthfully
- examples reflect the new config contract
- tests fail if benchmark metadata contract regresses

## Do not do in this package

- do not leave old README instructions as the primary product story
- do not let new artifact files exist undocumented
