# Risk Monitor Data Model

## Purpose

This document defines the data model that supports the evaluation dashboard (risk-monitor product layer) on top of Snowl.

## Layered model

The product is modeled as a layered flow:

1. **Benchmark metadata** — taxonomy contract defining domain, type, metric
2. **Trial outcomes** — per-trial results from eval execution
3. **Benchmark rollups** — per-benchmark aggregates grouped by model/variant
4. **Domain rollups** — per-domain aggregates across benchmarks
5. **Leaderboard rows** — flattened rows optimized for ranking and filtering
6. **Risk overview** — top-level dashboard summary
7. **UI projections** — frontend-rendered views

## Entity definitions

### Benchmark metadata

Defined in `snowl/benchmarks/base.py` as `BenchmarkInfo`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Unique benchmark identifier |
| `display_name` | str | Human-readable name |
| `description` | str | Full description |
| `domain` | str | Risk domain (e.g., cyber_offense, agentic_safety) |
| `benchmark_type` | str | "capability" or "safety" |
| `family` | str | Benchmark family (e.g., wmdp, strongreject) |
| `primary_metric` | str | Name of the primary evaluation metric |
| `higher_is_better` | bool | Whether higher values indicate better performance |
| `sample_preview_mode` | str | UI rendering hint: qa, dialog, tool_trace, gui_trace, code_trace |
| `dashboard_tags` | list[str] | Tags for filtering and categorization |

### Benchmark row

A benchmark-level aggregate for a given identity tuple. Written to `benchmark_summary.json`.

| Field | Type | Description |
|-------|------|-------------|
| `benchmark` | str | Benchmark name |
| `domain` | str | Risk domain |
| `benchmark_type` | str | "capability" or "safety" |
| `agent_id` | str | Agent identifier |
| `variant_id` | str | Variant identifier |
| `model` | str\|None | Model name |
| `primary_metric` | str | Primary metric name |
| `primary_metric_value` | float | Mean of primary metric across samples |
| `metric_means` | dict | All metric means |
| `sample_count` | int | Number of samples evaluated |
| `metadata` | dict | Model metadata (company, source_type, etc.) |

### Domain row

A domain-level aggregate over benchmark rows. Written to `domain_summary.json`.

| Field | Type | Description |
|-------|------|-------------|
| `domain` | str | Domain name |
| `capability_score` | float | Weighted mean of capability benchmark primary metrics |
| `safety_score` | float | Weighted mean of safety benchmark primary metrics |
| `risk_index` | float | Computed risk index |
| `benchmark_count` | int | Number of distinct benchmarks |
| `model_count` | int | Number of distinct models |

### Leaderboard row

A flattened row optimized for ranking and filtering. Written to `leaderboard_rows.jsonl`.

| Field | Type | Description |
|-------|------|-------------|
| `model` | str | Model name |
| `domain` | str | Domain name |
| `benchmark_type` | str | "capability" or "safety" |
| `primary_metric_mean` | float | Mean primary metric across benchmarks |
| `rank` | int | Rank within (domain, benchmark_type) group |
| `benchmarks_evaluated` | int | Number of benchmarks this model was evaluated on |
| `metadata` | dict | Model metadata for faceted filtering |

### Risk overview

Top-level dashboard summary. Computed by `build_risk_overview()`.

| Field | Type | Description |
|-------|------|-------------|
| `domains` | list[dict] | Domain rows |
| `total_models` | int | Total unique models |
| `total_benchmarks` | int | Total benchmarks across domains |
| `generated_at_utc` | str | Generation timestamp |

## Risk index computation

For domains with safety benchmarks:
```
risk_index = safety_weight * (1 - safety_score) + capability_weight * capability_score
```
Default weights: safety_weight=0.7, capability_weight=0.3.

For capability-only domains:
```
risk_index = capability_score
```

Weights are configurable via `beta_config` parameter.

## Model metadata

Optional metadata attached to model entries in `project.yml` for faceted filtering:

| Field | Type | Description |
|-------|------|-------------|
| `company` | str | Organization (e.g., "OpenAI", "Anthropic") |
| `country` | str | Country code (e.g., "US", "CN") |
| `source_type` | str | "open_source" or "closed_source" |
| `license_type` | str | License description |
| `reasoning` | str | "none", "low", "medium", "high", or "unknown" |
| `model_family` | str | Model family (e.g., "GPT-4", "Claude") |

## Schema versioning

- **v1**: Legacy run/summary artifacts (`aggregate.json` with `by_task_agent` and `matrix`)
- **v2**: Risk-monitor-native aggregate artifacts (`benchmark_summary.json`, `domain_summary.json`, `leaderboard_rows.jsonl`)

V1 and V2 artifacts coexist. V2 is additive; V1 remains for backward compatibility.

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/domains` | GET | List all domain summaries |
| `/api/domains/{domain}/overview` | GET | Domain detail with benchmarks |
| `/api/domains/{domain}/leaderboard` | GET | Ranked model rows (filter by `type=capability|safety`) |
| `/api/benchmarks` | GET | List all benchmarks with metadata |
| `/api/benchmarks/{name}` | GET | Benchmark detail |
| `/api/benchmarks/{name}/samples` | GET | Sample preview cards |

Existing endpoints (`/api/runs`, `/api/experiments`, etc.) are unchanged.
