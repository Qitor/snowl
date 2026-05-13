# Custom Benchmark Adapter

Create and run your own benchmark adapter for private datasets, experimental
benchmarks, or team-specific evaluation packs.

---

## Scaffold a new adapter

```bash
snowl bench scaffold mybench --out ./mybench
```

This creates:

```
mybench/
  adapter.py     # Adapter implementation
  data.jsonl     # Sample dataset
  README.md      # Documentation
```

## Implement the adapter

Subclass `BaseBenchmarkAdapter` and implement three methods:

```python
# mybench/adapter.py
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.base import BenchmarkInfo
from snowl.core import EnvSpec

class MyBenchmarkAdapter(BaseBenchmarkAdapter[dict]):
    name: str = "my_benchmark"
    description: str = "My custom benchmark"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            display_name="My Benchmark",
            domain="agentic_safety",
            benchmark_type="safety",
            primary_metric="safety_score",
            higher_is_better=True,
        )

    def _row_to_sample(self, row, *, row_index, row_split, selected_count):
        return {
            "id": f"my-bench-{row_index}",
            "input": row["prompt"],
            "metadata": {"split": row_split, **row.get("metadata", {})},
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
```

### Dataset row conventions

The scaffold uses JSONL rows:

```json
{"id":"sample-1","split":"test","input":"Say hello.","target":"hello","category":"smoke"}
```

Recommended fields:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable sample identity |
| `split` | No | `test`, `dev`, `train`, or benchmark-specific |
| `input` or `messages` | Yes | Prompt payload |
| `target` | No | Expected output for scorer comparison |
| `category` | No | Category for grouped metrics |

Keep IDs stable. Snowl uses them in trial keys, retry ledgers, and dashboards.

## Validate the adapter

```bash
snowl bench check mybench \
  --adapter ./mybench/adapter.py:MyBenchmarkAdapter \
  --adapter-arg dataset_path=./mybench/data.jsonl
```

## Run the adapter

```bash
snowl bench run mybench \
  --adapter ./mybench/adapter.py:MyBenchmarkAdapter \
  --adapter-arg dataset_path=./mybench/data.jsonl \
  --project ./project.yml \
  --split test \
  --limit 10
```

## Adapter object forms

The `--adapter` value (`module.py:object`) can export:

- An adapter instance
- A factory function that accepts `--adapter-arg` keyword values
- A `BenchmarkAdapter` subclass

Snowl normalizes the object to an adapter instance and runs conformance checks.

## Split, limit, and filter behavior

```bash
snowl bench run mybench --split test --limit 10 --benchmark-filter category=safety
```

- `--split test` filters rows to the matching split
- `--limit 10` caps the number of samples loaded
- `--benchmark-filter key=value` passes filter key-value pairs to the adapter

## Sample metadata

Include benchmark identity and taxonomy in sample metadata:

```python
metadata = {
    "benchmark": "mybench",
    "split": "test",
    "domain": "cyber_offense",
    "benchmark_type": "safety",
    "family": "mybench",
    "primary_metric": "accuracy",
    "target": row.get("target"),
}
```

Sample metadata is passed to scorers as `context.sample_metadata`.

## Suite integration

Combine built-in and external adapters in one suite:

```yaml
# suite.yml
suite:
  name: safety-smoke
  project: ./project.yml
  split: test
  limit: 10
  benchmarks:
    - name: strongreject
    - name: mybench
      adapter: ./mybench/adapter.py:MyBenchmarkAdapter
      adapter_args:
        dataset_path: ./mybench/data.jsonl
```

```bash
snowl suite check suite.yml
snowl suite run suite.yml
```

Suite execution is sequential. Each child benchmark is a normal Snowl run with
its own artifacts.
