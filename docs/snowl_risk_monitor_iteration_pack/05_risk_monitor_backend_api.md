# Package 5: Risk Monitor Backend API

## Goal

Extend the current monitor backend from a run indexer into a dual-purpose store that supports both operator workflows and risk portfolio views.

## Directly affected files

- `snowl/web/monitor.py`
- `tests/test_web_monitor_store.py`
- `tests/test_eval_web_observability.py`
- `tests/test_monitor_leaderboards.py` (new)

## Current state

The monitor backend already supports:
- run listing
- experiment listing
- run snapshots
- experiment summaries

That should remain intact.

## New backend entities

Add first-class aggregated entities:
- `domains`
- `benchmarks`
- `leaderboard_rows`

Suggested internal tables:
- `domain_rows`
- `benchmark_rows`
- `leaderboard_rows`

## Required API additions

Add:
- `GET /api/domains`
- `GET /api/domains/{domain}/overview`
- `GET /api/domains/{domain}/leaderboard?type=capability|safety`
- `GET /api/benchmarks`
- `GET /api/benchmarks/{benchmark_name}`
- `GET /api/benchmarks/{benchmark_name}/samples`

Keep existing endpoints unchanged:
- `/api/runs`
- `/api/runs/{id}/summary`
- `/api/experiments`
- `/api/experiments/{id}/summary`

## Implementation guidance

### 1. Extend ingestion path

When indexing a finished run, read:
- `benchmark_summary.json`
- `domain_summary.json`
- `leaderboard_rows.jsonl`

If v2 artifacts are absent, degrade gracefully.

### 2. Add benchmark/domain materialization step

The monitor should materialize:
- benchmark overview rows
- domain overview rows
- leaderboard rows

This can be done incrementally during run indexing.

### 3. Preserve operator API semantics

Do not rewrite old endpoints to emulate risk views.
Add new risk-native endpoints instead.

## Acceptance criteria

- existing run and experiment views still work
- risk dashboard can load from new domain/benchmark endpoints
- benchmark sample API returns previewable rows

## Do not do in this package

- do not remove existing run-oriented APIs
- do not force frontend to derive leaderboards client-side
