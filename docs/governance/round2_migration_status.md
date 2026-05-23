# Round 2 Migration Status

Date: 2026-05-23

## Baseline

- Test suite: 662 passed, 0 failed, 9 skipped
- Fixed: `toolemu/scorer.py` sys.path.insert (replaced with `_path_inserter` indirection + `importlib` imports)
- Dependency guard test: PASSING

## Selected First Migration Batch

| Benchmark | Location | Adapter Class | Scorer? | Migrated? |
|-----------|----------|---------------|---------|-----------|
| strongreject | `snowl_evals/strongreject/` | StrongRejectBenchmarkAdapter | Yes | Yes |
| xstest | `snowl_evals/xstest/` | XSTestBenchmarkAdapter | Yes | Yes |
| wmdp | `snowl_evals/wmdp/` | WMDPBenchmarkAdapter | No | Yes |
| sec_qa | `snowl_evals/sec_qa/` | SecQABenchmarkAdapter | No | Yes |
| cybermetric | `snowl_evals/cybermetric/` | CyberMetricBenchmarkAdapter | No | Yes |

## Benchmarks with Manifests

All 21 benchmark directories have `benchmark.yaml` manifests:
- agentdojo, agent_bench_os, agentharm, agentsafetybench, bfcl, coconot,
  cybermetric, exploitbench, fortress, ipi_coding_agent, mask, osworld,
  sec_qa, sevenllm, strongreject, terminalbench, toolemu, wmdp, xstest
- Generic adapters: jsonl_adapter.yaml, csv_adapter.yaml

## snowl-evals Prototype

- **Location**: `external/snowl-evals-prototype/`
- **Installable**: `pip install -e external/snowl-evals-prototype`
- **Entry points**: 10 entries (strongreject, xstest, wmdp-cyber, wmdp-chem, sec_qa_v1, sec_qa_v2, cybermetric_80/500/2000/10000)
- **Prototype tests**: 18 passed (entrypoints + manifest validation)
- **Code duplication**: Temporary — adapter code duplicated between snowl and snowl-evals prototype

## Compatibility Shims

| Benchmark | Shim Location | Deprecation Warning | Status |
|-----------|--------------|-------------------|--------|
| strongreject | `snowl/benchmarks/strongreject/__init__.py` | Yes | Done |
| Others | N/A | Not yet | Pending |

Strategy: One benchmark shimmed as proof of concept; remaining benchmarks
will get shims when the final migration happens.

## Plugin Discovery

- **Verified**: `snowl bench list` shows built-in and plugin benchmarks with source column
- **Verified**: Plugin-only registry loads all 10 entries from snowl-evals
- **Verified**: Broken entry points emit warnings, not crashes
- **Verified**: `snowl bench doctor` runs diagnostic checks

## Bench List Output

New tabular format with Source column:
```
Name                     Source     Type         Domain             Primary Metric
-------------------------------------------------------------------------------------
strongreject             plugin     safety       agentic_safety     strongreject
cybermetric_80           plugin     capability   cyber_offense      accuracy
jsonl                    built-in   capability   uncategorized      custom
```

## Bench Doctor

`snowl bench doctor` checks:
1. Core snowl import
2. Registry load
3. Plugin discovery status
4. Broken entry points
5. Missing manifests
6. Manifest validation
7. Heavy runtime benchmarks

## Remaining Blockers

None — all round 2 objectives met.

## Remaining TODOs

- Migrate remaining benchmarks to snowl-evals (coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent)
- Add compatibility shims for all migrated benchmarks
- Heavy benchmark migration (agentdojo, toolemu, agentsafetybench, terminalbench, osworld, exploitbench)
- CI pipeline for snowl-evals
- PyPI publication of snowl-evals
- Remove duplicated adapter code from snowl once migration is finalized