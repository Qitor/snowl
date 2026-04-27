# Risk Monitor Data Model

## Purpose

This document defines the data model needed to support a risk-monitor product layer on top of snowl.

## Layered model

The product should be modeled as a layered flow:

1. **Benchmark metadata**
2. **Trial outcomes**
3. **Benchmark rollups**
4. **Domain rollups**
5. **Leaderboard rows**
6. **Risk overview**
7. **UI projections**

## Entity definitions

### Benchmark metadata
Fields:
- `name`
- `display_name`
- `domain`
- `benchmark_type`
- `family`
- `primary_metric`
- `higher_is_better`
- `sample_preview_mode`
- `dashboard_tags`

### Trial outcome
Fields:
- `run_id`
- `experiment_id`
- `benchmark`
- `domain`
- `benchmark_type`
- `model`
- `variant_id`
- `company`
- `country`
- `source_type`
- `reasoning`
- `score`
- `normalized_score`
- `pass_rate`
- `artifact_paths`

### Benchmark row
A benchmark-level aggregate for a given identity tuple.

Identity tuple recommendation:
- `benchmark`
- `model`
- `variant_id`
- `company`
- `source_type`
- `reasoning`

Metrics:
- `primary_metric_value`
- `sample_count`
- `completed_trials`
- `success_rate`
- `safety_rate`
- `timestamp_range`

### Domain row
A domain-level aggregate over benchmark rows.

Fields:
- `domain`
- `model`
- `variant_id`
- `capability_score`
- `safety_score`
- `risk_index`
- `benchmark_count`
- `benchmark_coverage`

### Leaderboard row
A flattened row optimized for rendering and filtering.

Fields:
- `domain`
- `benchmark_type`
- `model`
- `company`
- `country`
- `source_type`
- `reasoning`
- `capability_score`
- `safety_score`
- `risk_index`

### Risk overview
Top-level homepage summary.

Fields:
- `domain_cards`
- `top_capability_rows`
- `top_safety_rows`
- `highest_risk_rows`
- `coverage_summary`
- `latest_benchmarks`

## Design principles

- operator views and risk views should share artifacts but not share presentation assumptions
- benchmark-domain mapping belongs in backend metadata, not in frontend hardcoded logic
- risk dashboard must consume pre-aggregated rows, not derive everything client-side
- all new entities should tolerate partial adoption during migration

## Versioning

Use schema versioning for all new aggregate payloads.

Recommended:
- `v1`: legacy run/summary artifacts
- `v2`: risk-monitor-native aggregate artifacts
