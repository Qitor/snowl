# Third-Party Benchmark Adapter SDK v0

Snowl can run a benchmark without adding it to the built-in registry. Use this path when you are experimenting with a private dataset, evaluating a paper benchmark before upstreaming it, or building a local benchmark pack for a team.

## Fast Path

Create a template:

```bash
snowl bench scaffold mybench --out ./mybench
```

Check the adapter:

```bash
snowl bench check mybench \
  --adapter ./mybench/adapter.py:adapter \
  --adapter-arg dataset_path=./mybench/data.jsonl
```

Run it with any Snowl project:

```bash
snowl bench run mybench \
  --adapter ./mybench/adapter.py:adapter \
  --adapter-arg dataset_path=./mybench/data.jsonl \
  --project ./project.yml \
  --split test \
  --limit 10
```

The `--adapter` value is local-file based and uses `module.py:object`.

## Adapter Object Forms

The exported object can be any of these:

- an adapter instance
- a factory function that accepts `--adapter-arg` keyword values
- a `BenchmarkAdapter` subclass

Snowl normalizes the object to an adapter instance and runs conformance checks against the same contract used by built-in benchmarks.

## Contract

An adapter must expose:

```python
info: BenchmarkInfo
list_splits() -> list[str]
load_tasks(split: str, limit: int | None = None, filters: dict | None = None) -> list[Task]
```

Most row-oriented datasets should subclass `BaseBenchmarkAdapter` and implement:

- `_iter_rows`
- `_row_split`
- `_row_to_sample`

Each sample should have a stable `id` and either `input` or `messages`.

## Dataset Row Conventions

The scaffold uses JSONL rows:

```json
{"id":"sample-1","split":"test","input":"Say hello.","target":"hello","category":"smoke"}
```

Recommended fields:

- `id`: stable sample identity
- `split`: `test`, `dev`, `train`, or benchmark-specific split
- `input` or `messages`: prompt payload
- `target`: optional scorer reference
- metadata fields such as `category`, `source`, `difficulty`, `risk_area`

Keep ids stable. Snowl uses them in trial keys, retry ledgers, artifacts, and dashboards.

## Split, Limit, And Filter Behavior

`snowl bench run ... --split test --limit 10` calls:

```python
adapter.load_tasks(split="test", limit=10, filters={...})
```

`--benchmark-filter key=value` values are passed through as `filters`. If you subclass `BaseBenchmarkAdapter`, filtering is handled before `_row_to_sample`.

## Metadata And Artifact Propagation

Task metadata should include benchmark identity and useful taxonomy:

```python
{
  "benchmark": "mybench",
  "split": "test",
  "domain": "cyber_offense",
  "benchmark_type": "safety",
  "family": "mybench",
  "primary_metric": "accuracy"
}
```

Sample metadata is passed to scorers as `context.sample_metadata`. Put scorer references such as `target`, `expected`, `category`, or parser hints there.

Run artifacts keep the normal Snowl layout under `.snowl/runs/<run_id>/`, including `manifest.json`, `plan.json`, `events.jsonl`, `outcomes.json`, `aggregate.json`, and benchmark rollups.

## Scorer Expectations

One benchmark run still uses the scorer loaded from the Snowl project. Your project can either:

- use a generic scorer such as text includes/match logic
- import a benchmark-specific scorer from your adapter folder
- compose several scorers in project code

For external adapters, prefer clear metric names (`accuracy`, `pass_rate`, `refusal`, `harmfulness`) and return `snowl.core.Score` values.

## Suites

You can combine built-in and external adapters in one suite:

```yaml
suite:
  name: safety-smoke
  project: ./project.yml
  split: test
  limit: 10
  benchmarks:
    - name: strongreject
      adapter_args:
        dataset_path: ./data/strongreject.csv
    - name: mybench
      adapter: ./mybench/adapter.py:adapter
      adapter_args:
        dataset_path: ./mybench/data.jsonl
runtime:
  max_running_trials: 4
  max_scoring_tasks: 4
  provider_budgets:
    default: 4
```

Validate and run:

```bash
snowl suite check suite.yml
snowl suite run suite.yml
```

Suite execution is sequential in SDK v0. Each child benchmark is a normal Snowl run with its own artifacts; the suite summary is written to `.snowl/suites/<suite_run_id>/suite_summary.json`.
