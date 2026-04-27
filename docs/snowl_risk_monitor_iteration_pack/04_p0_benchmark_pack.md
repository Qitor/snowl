# Package 4: P0 Benchmark Pack

## Goal

Onboard the first batch of benchmarks that best support a portfolio-style risk dashboard.

## Benchmark priority for this iteration

### Must complete

1. `wmdp-cyber`
2. `wmdp-chem`
3. `strongreject` uplift to first-class dashboard benchmark
4. `mask`

### Stretch goals

5. `sciknoweval-biological-harmfulqa`
6. `sosbench-chem`

### Defer to later iteration

- `cyberseceval2-vulnerabilityexploit`
- `lab-bench-seqqa`
- `lab-bench-cloningscenarios`
- `biolp-bench`

## Why this is the right first batch

This set gives you:
- capability-side coverage with relatively low integration friction
- safety-side coverage with dashboard-friendly outputs
- at least one benchmark already present in snowl (`strongreject`)
- a clearer path to domain pages and benchmark detail views

## Directly affected files

### WMDP
- `snowl/benchmarks/wmdp/__init__.py` (new)
- `snowl/benchmarks/wmdp/adapter.py` (new)
- `snowl/benchmarks/registry.py`
- `examples/wmdp-cyber-official/project.yml` (new)
- `examples/wmdp-chem-official/project.yml` (new)
- `tests/test_wmdp_cyber_benchmark.py` (new)
- `tests/test_wmdp_chem_benchmark.py` (new)

### StrongReject uplift
- `snowl/benchmarks/strongreject/*`
- `snowl/benchmarks/registry.py`
- `snowl/aggregator/summary.py`
- `examples/strongreject-official/project.yml` (new or updated)
- `tests/test_strongreject_benchmark.py`

### MASK
- `snowl/benchmarks/mask/__init__.py` (new)
- `snowl/benchmarks/mask/adapter.py` (new)
- `snowl/benchmarks/registry.py`
- `examples/mask-official/project.yml` (new)
- `tests/test_mask_benchmark.py` (new)

## Adapter requirements

Every new benchmark adapter must implement:
- `benchmark_info()`
- normalized primary metric
- `sample_card(row)`
- consistent trial metadata
- dashboard-friendly sample payloads

## Acceptance criteria

- all four P0 benchmarks appear in benchmark list output
- each has domain and benchmark type metadata
- each emits benchmark/domain rollups
- each can be surfaced in benchmark detail UI

## Do not do in this package

- do not chase environment-heavy benchmarks too early
- do not add placeholder adapters that cannot produce stable metrics
