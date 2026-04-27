# snowl Risk Monitor Foundation Pack

This zip contains a concrete, file-linked iteration package for evolving **snowl** from a run-centric agent evaluation framework into a **risk-monitor-native** evaluation platform that can support an AIRiskMonitor-style presentation layer.

## Included documents

- `00_iteration_summary.md`
- `01_benchmark_taxonomy_contract.md`
- `02_artifact_schema_v2_and_finalize_convergence.md`
- `03_model_metadata_and_filters.md`
- `04_p0_benchmark_pack.md`
- `05_risk_monitor_backend_api.md`
- `06_frontend_split_risk_vs_runs.md`
- `07_docs_and_tests_sync.md`
- `08_codex_execution_plan.md`
- `docs/risk_monitor_data_model.md`
- `docs/benchmark_taxonomy.md`
- `docs/benchmark_onboarding_playbook.md`

## Intended use

This pack is designed to be handed directly to Codex or another coding agent as the basis for the next iteration.

The central product goal of this iteration is:

> make snowl produce **dashboard-native risk artifacts** rather than only run-native operator artifacts.

## Scope of this iteration

Do now:
- benchmark taxonomy contract
- artifact schema v2
- benchmark/domain/leaderboard rollups
- model metadata for faceted filtering
- first batch of dashboard-friendly benchmark integrations
- risk monitor backend APIs
- homepage split between risk dashboard and operator views
- documentation and tests synchronization

Defer:
- full distributed scheduling
- multi-provider runtime redesign
- complete phase-aware scheduler rewrite
- large-scale environment-heavy benchmark onboarding
