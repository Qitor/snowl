# Package 2: Artifact Schema v2 and Finalize Convergence

## Goal

Make snowl emit artifacts that a risk dashboard can consume directly, while also closing the current gap between repo-level eval flow and standalone `execute_trial()` finalization semantics.

## Directly affected files

- `snowl/aggregator/schema.py`
- `snowl/aggregator/summary.py`
- `snowl/eval.py`
- `snowl/runtime/engine.py`
- `tests/test_aggregator_summary.py`
- `tests/test_eval_artifact_schema.py`
- `tests/test_runtime_engine.py`
- `tests/test_risk_rollups.py` (new)

## Current problem

The current aggregation model is centered around:
- identity rows
- task-agent grouping
- matrix output
- run/expt summaries

This is useful for operator workflows, but insufficient for:
- domain pages
- benchmark detail pages
- leaderboard tables
- risk overview cards

## Required code changes

### 1. Add schema v2 in `snowl/aggregator/schema.py`

Introduce:

```python
RESULT_SCHEMA_VERSION = "v2"

BENCHMARK_SUMMARY_SCHEMA_URI = "..."
DOMAIN_SUMMARY_SCHEMA_URI = "..."
LEADERBOARD_ROW_SCHEMA_URI = "..."
```

Preserve backward compatibility where practical.

### 2. Refactor aggregation pipeline in `snowl/aggregator/summary.py`

Split the current aggregation logic into explicit layers:

```python
def aggregate_identity_rows(outcomes): ...
def aggregate_benchmark_rows(outcomes, benchmark_metadata): ...
def aggregate_domain_rows(benchmark_rows): ...
def compute_risk_index(domain_rows, beta_config): ...
def build_risk_overview(domain_rows, leaderboard_rows): ...
```

### 3. Add new output sections to aggregate payload

`aggregate.json` should include:
- `by_task_agent`
- `benchmark_rows`
- `domain_rows`
- `leaderboard_rows`
- `risk_overview`

### 4. Emit first-class files in `snowl/eval.py`

After a run finishes, also write:
- `benchmark_summary.json`
- `domain_summary.json`
- `leaderboard_rows.jsonl`

Update `manifest.json` to include:
- `benchmark_info`
- `domain`
- `benchmark_type`
- `aggregation_schema_version`
- new research export paths

### 5. Converge finalize behavior

Without doing a full scheduler rewrite, make sure repo-level eval and standalone `execute_trial()` both produce the same final artifact set.

At minimum:
- repo-level execution must always run the finalize artifact path
- missing benchmark/domain rollups should be impossible in a successful run

## Risk index recommendation

Implement risk index computation behind config, but provide a default baseline that can later mirror AIRiskMonitor-like weighting rules.

Suggested starting config:

```yaml
risk_index:
  source_type_beta:
    open_source: 0.6
    closed_source: 0.8
```

## Acceptance criteria

- completed runs emit benchmark/domain/leaderboard summaries
- successful runs always have complete v2 artifact set
- compare workflow remains functional
- existing operator APIs keep working

## Do not do in this package

- do not redesign scheduler admission control
- do not add distributed execution
- do not break existing `summary.json` consumers without compatibility layer
