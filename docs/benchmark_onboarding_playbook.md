# Benchmark Onboarding Playbook

## Purpose

This playbook defines the minimum requirements for onboarding a benchmark into Snowl in a way that supports both execution and the evaluation dashboard.

There are two supported paths:

- **Third-party/local adapter**: use `snowl bench scaffold` and run with `--adapter module.py:object`. This is the fastest path for private, experimental, or team-local benchmarks. It does not require registry edits.
- **Built-in adapter**: add package code and registry metadata under `snowl/benchmarks/`. Use this for benchmarks Snowl ships and maintains.

See [third_party_benchmark_adapter.md](./third_party_benchmark_adapter.md) for the local adapter SDK.

## Every benchmark onboarding must include

1. **Adapter implementation** — subclass `BaseBenchmarkAdapter` when possible
2. **Benchmark metadata contract** — override `benchmark_info()` with full taxonomy
3. **Sample preview contract** — override `sample_card()` for UI rendering when the default preview is not enough
4. **Trial metadata** — override `trial_metadata()` for benchmark-specific annotations
5. **Example project config or local README** — document how to run the benchmark
6. **Tests or conformance check** — add focused tests for built-ins; run `snowl bench check` for local adapters
7. **Documentation entry** — update `docs/benchmark_taxonomy.md` for built-ins

Built-in adapters also need a **registry entry** in `snowl/benchmarks/registry.py`. Third-party adapters can skip registry edits and use `--adapter`.

## Required metadata fields

Every adapter must expose via `benchmark_info()`:

| Field | Required | Example |
|-------|----------|---------|
| `name` | Yes | "wmdp-cyber" |
| `description` | Yes | "WMDP-Cyber benchmark adapter." |
| `display_name` | Auto (defaults to name) | "WMDP Cyber" |
| `domain` | Yes | "cyber_offense" |
| `benchmark_type` | Yes | "capability" or "safety" |
| `family` | Auto (defaults to name) | "wmdp" |
| `primary_metric` | Yes | "accuracy" |
| `higher_is_better` | Yes | True |
| `sample_preview_mode` | Yes | "qa" |
| `dashboard_tags` | Recommended | ["mcq", "cybersecurity"] |

## Required adapter hooks

### `benchmark_info(self) -> BenchmarkInfo`
Returns normalized metadata. For most adapters, the registry entry provides this via the default lookup. Override only if the adapter needs dynamic metadata.

### `sample_card(self, row: dict) -> dict`
Returns a preview payload suitable for the benchmark detail UI. Must include at least `id` and `input_preview`.

### `trial_metadata(self, task: dict) -> dict`
Returns benchmark-specific trial annotations needed for aggregation or rendering.

## Template adapter

```python
from dataclasses import dataclass
from typing import Any
from snowl.benchmarks.base import BenchmarkInfo
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter

@dataclass(frozen=True)
class MyBenchmarkAdapter(BaseBenchmarkAdapter[dict[str, Any]]):
    dataset_path: str = ""
    name: str = "my-benchmark"
    description: str = "My benchmark adapter."
    default_split: str = "test"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            description=self.description,
            domain="my_domain",
            benchmark_type="capability",
            family="my-family",
            primary_metric="accuracy",
            higher_is_better=True,
            sample_preview_mode="qa",
            dashboard_tags=["tag1", "tag2"],
        )

    def sample_card(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "input_preview": str(row.get("question", ""))[:200],
        }

    def trial_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"scoring": "accuracy"}

    def _iter_rows(self) -> list[dict[str, Any]]:
        # Load your dataset here
        ...

    def _row_split(self, row: dict[str, Any], *, row_index: int) -> str:
        return str(row.get("split", "test"))

    def _row_to_sample(
        self, row: dict[str, Any], *, row_index: int, row_split: str, selected_count: int,
    ) -> dict[str, Any] | None:
        question = str(row.get("question", "")).strip()
        if not question:
            return None
        return {
            "id": row.get("id", f"sample-{row_index}"),
            "input": question,
            "metadata": {"split": row_split},
        }
```

## Onboarding checklist

- [ ] Adapter implemented with all required hooks
- [ ] Metadata normalized with domain, benchmark_type, primary_metric
- [ ] Local adapter passes `snowl bench check ... --adapter module.py:object`, or built-in adapter is registered
- [ ] Example config added to `examples/` for built-ins, or adapter README added for third-party benchmarks
- [ ] Tests added to `tests/`
- [ ] Built-in benchmark appears in `snowl bench list` with full metadata
- [ ] Benchmark produces stable v2 rollups (benchmark_summary.json, domain_summary.json)
- [ ] Benchmark is visible in dashboard data APIs (`/api/benchmarks`)
- [ ] `docs/benchmark_taxonomy.md` updated

## Anti-patterns

Do not:
- Add registry entries without metadata
- Hide benchmark-domain mapping only in frontend code
- Merge unstable placeholder integrations just to expand the list
- Add benchmark-specific hacks to shared layers when a contract extension is cleaner
