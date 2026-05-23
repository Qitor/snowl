# Adding a Benchmark to snowl-evals

This guide explains how to add a new benchmark adapter to the `snowl-evals`
package.

## Step 1: Create the package directory

```
snowl_evals/
  mybench/
    __init__.py
    adapter.py
    benchmark.yaml
```

## Step 2: Implement the adapter

Create `adapter.py` subclassing `BaseBenchmarkAdapter` from `snowl`:

```python
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter


@dataclass(frozen=True)
class MyBenchAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str
    name: str = "mybench"
    description: str = "My benchmark adapter."

    def _iter_rows(self) -> list[dict[str, Any]]:
        ...

    def _row_split(self, row, *, row_index: int) -> str:
        ...

    def _row_to_sample(self, row, *, row_index, row_split, selected_count):
        ...
```

## Step 3: Add a benchmark manifest

Create `benchmark.yaml` following the `snowl.benchmark_manifest.v1` schema:

```yaml
schema_version: snowl.benchmark_manifest.v1
name: mybench
display_name: My Benchmark
family: mybench
domain: agentic_safety
benchmark_type: safety
primary_metric: my_score
higher_is_better: true
status: stable

source:
  paper: null
  code: null
  license: null

adapter:
  entrypoint: snowl_evals.mybench.adapter:MyBenchAdapter
  min_snowl_version: "0.1.0"

runtime:
  env_type: local
  requires_docker: false

data:
  included: false
  download_required: true

scoring:
  method: custom
  judge_model_required: false

reproducibility:
  deterministic: true
  seed_supported: true

migration:
  target: snowl-evals
  phase: phase_2_simple
  priority: medium
```

## Step 4: Create the register function

In `__init__.py`, expose a `register(registry)` function:

```python
from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.registry import _lazy_factory


def register(registry) -> None:
    registry.register(
        name="mybench",
        info=BenchmarkInfo(
            name="mybench",
            description="My benchmark adapter.",
        ),
        factory=_lazy_factory("snowl_evals.mybench.adapter", "MyBenchAdapter"),
    )
```

## Step 5: Add entry point

In `pyproject.toml`:

```toml
[project.entry-points."snowl.benchmarks"]
mybench = "snowl_evals.mybench:register"
```

## Step 6: Test

```bash
pip install -e .
snowl bench list           # Should show mybench
snowl bench check mybench  # Run conformance checks
```
