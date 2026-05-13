# Benchmarks API

Benchmark adapter base classes and registry.

## BaseBenchmarkAdapter

The abstract base class for row-oriented benchmark adapters. Subclass this and
implement `_iter_rows`, `_row_split`, and `_row_to_sample`.

```python
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
```

## BenchmarkInfo

Metadata about a benchmark adapter:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Registry name |
| `display_name` | `str` | Human-readable name |
| `domain` | `str` | Domain (e.g., `agentic_safety`) |
| `benchmark_type` | `str` | Type (e.g., `safety`, `capability`) |
| `primary_metric` | `str` | Main metric name |
| `higher_is_better` | `bool` | Metric direction |

## Registry

Built-in adapters are registered in `snowl/benchmarks/registry.py`. Access via:

```bash
snowl bench list
```

## Key adapter classes

| Adapter | Module |
|---------|--------|
| `StrongRejectBenchmarkAdapter` | `snowl.benchmarks.strongreject` |
| `ToolEmuBenchmarkAdapter` | `snowl.benchmarks.toolemu` |
| `AgentDojoBenchmarkAdapter` | `snowl.benchmarks.agentdojo` |
| `AgentHarmBenchmarkAdapter` | `snowl.benchmarks.agentharm` |
| `XSTestBenchmarkAdapter` | `snowl.benchmarks.xstest` |
| `BFCLBenchmarkAdapter` | `snowl.benchmarks.bfcl` |
| `TerminalBenchBenchmarkAdapter` | `snowl.benchmarks.terminalbench` |
| `OSWorldBenchmarkAdapter` | `snowl.benchmarks.osworld` |
| `WMDPBenchmarkAdapter` | `snowl.benchmarks.wmdp` |
| `CyberMetricBenchmarkAdapter` | `snowl.benchmarks.cybermetric` |
| `SecQABenchmarkAdapter` | `snowl.benchmarks.sec_qa` |
| `SevenLLMMCQBenchmarkAdapter` | `snowl.benchmarks.sevenllm` |
| `JsonlBenchmarkAdapter` | `snowl.benchmarks.jsonl` |
| `CsvBenchmarkAdapter` | `snowl.benchmarks.csv` |
