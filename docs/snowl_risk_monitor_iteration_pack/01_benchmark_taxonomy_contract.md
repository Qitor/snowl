# Package 1: Benchmark Taxonomy Contract

## Goal

Upgrade benchmark metadata from a minimal registry entry into a dashboard-ready taxonomy contract.

## Why this change is necessary

Current benchmark metadata is too thin to drive:
- domain leaderboards
- capability vs safety views
- benchmark family navigation
- sample preview rendering
- risk-level aggregation

Without this change, any AIRiskMonitor-style UI will be forced to hardcode logic in the frontend.

## Directly affected files

- `snowl/benchmarks/base.py`
- `snowl/benchmarks/base_adapter.py`
- `snowl/benchmarks/registry.py`
- `snowl/bench.py`
- `tests/test_benchmark_registry_and_cli.py`
- `tests/test_benchmark_metadata_contract.py` (new)

## Required code changes

### 1. Extend `BenchmarkInfo` in `snowl/benchmarks/base.py`

Add at least these fields:

```python
@dataclass(frozen=True)
class BenchmarkInfo:
    name: str
    display_name: str
    description: str
    short_description: str
    domain: str
    benchmark_type: str  # capability | safety
    family: str
    primary_metric: str
    higher_is_better: bool
    sample_preview_mode: str  # qa | dialog | tool_trace | gui_trace | code_trace
    dashboard_tags: list[str]
```

### 2. Extend adapter contract in `snowl/benchmarks/base_adapter.py`

Add hooks:

```python
def benchmark_info(self) -> BenchmarkInfo: ...
def sample_card(self, row: dict) -> dict: ...
def trial_metadata(self, task: dict) -> dict: ...
```

### 3. Populate metadata in `snowl/benchmarks/registry.py`

For current built-ins, define explicit metadata. First-pass mapping:

- `strongreject`
  - `benchmark_type="safety"`
  - `family="strongreject"`
  - `domain="agentic_safety"` or `"cross_domain"`
- `terminalbench`
  - `benchmark_type="capability"`
  - `family="terminalbench"`
  - `domain="cyber_offense"`
- `osworld`
  - `benchmark_type="capability"`
  - `family="osworld"`
  - `domain="cyber_offense"` or `"agentic_capability"`
- `toolemu`
  - `benchmark_type="safety"`
  - `family="toolemu"`
  - `domain="agentic_safety"`
- `agentsafetybench`
  - `benchmark_type="safety"`
  - `family="agentsafetybench"`
  - `domain="agentic_safety"`

### 4. Upgrade benchmark listing in `snowl/bench.py`

Change `list_benchmarks()` to return the full benchmark metadata, not only `name` and `description`.

### 5. Add validation tests

Create `tests/test_benchmark_metadata_contract.py` to enforce:
- required fields are present
- `benchmark_type` is one of allowed values
- `domain` is non-empty and normalized
- `primary_metric` is set
- `sample_preview_mode` is set

## Acceptance criteria

- `snowl bench list --json` includes `domain`, `benchmark_type`, `family`, `primary_metric`
- all built-in adapters pass contract validation
- frontend/backend no longer need hardcoded benchmark-domain mappings

## Do not do in this package

- do not redesign the runtime
- do not add heavy benchmark logic here
- do not put domain-mapping logic only in frontend code
