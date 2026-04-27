# Benchmark Onboarding Playbook

## Purpose

This playbook defines the minimum requirements for onboarding a benchmark into snowl in a way that supports both execution and risk monitoring.

## Every benchmark onboarding must include

1. adapter implementation
2. registry entry
3. benchmark metadata contract
4. sample preview contract
5. example project config
6. tests
7. documentation entry

## Required metadata

Every adapter must expose:

- `name`
- `display_name`
- `domain`
- `benchmark_type`
- `family`
- `primary_metric`
- `higher_is_better`
- `sample_preview_mode`
- `dashboard_tags`

## Required adapter behaviors

### `benchmark_info()`
Returns normalized metadata.

### `sample_card(row)`
Returns a preview payload suitable for the benchmark detail UI.

### `trial_metadata(task)`
Returns benchmark-specific trial annotations needed for aggregation or rendering.

## Required tests

- registry registration test
- metadata contract test
- smoke execution test
- sample preview serialization test
- aggregation compatibility test

## Required docs

At onboarding time, update:
- `README.md` or benchmark index section
- `docs/benchmark_taxonomy.md`
- relevant example configs

## Onboarding checklist

- [ ] adapter implemented
- [ ] metadata normalized
- [ ] example config added
- [ ] tests added
- [ ] benchmark appears in `snowl bench list --json`
- [ ] benchmark emits stable rollups
- [ ] benchmark is visible in dashboard data APIs

## Anti-patterns

Do not:
- add registry entries without metadata
- hide benchmark-domain mapping only in frontend code
- merge unstable placeholder integrations just to expand the list
