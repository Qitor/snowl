# Deprecation Policy for Benchmark Migration

## Overview

This document describes the deprecation policy for benchmark adapters migrating
from the `snowl` core repository to the standalone `snowl-evals` package.

## Current State

### Migrated benchmarks (phase_2_simple)

All 13 phase_2_simple benchmarks have been migrated to `snowl-evals`:

- strongreject, xstest, wmdp, sec_qa, cybermetric
- coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent

### Transition policy

During the transition period:

1. **Built-in adapters remain in `snowl/benchmarks/<name>/`** — they still work as before
2. **Compatibility shims emit `DeprecationWarning`** — importing from `snowl.benchmarks.<name>` warns users
3. **Built-in wins over plugin** — when both built-in and `snowl-evals` register the same name, the built-in entry is canonical
4. **Plugin duplicates are shadowed** — `snowl-evals` entries are stored but not used for the canonical entry
5. **`snowl bench doctor` reports** — shadowed entries and migrated benchmarks using built-in fallback

### Import migration

Users should migrate imports from:

```python
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
```

to:

```python
from snowl_evals.strongreject import StrongRejectBenchmarkAdapter
```

Both paths work during the transition period. The old path emits a `DeprecationWarning`.

## Removal Timeline

After at least **two minor releases** with deprecation warnings:

1. Remove the built-in adapter implementation directories (`snowl/benchmarks/<name>/`)
2. Remove `_lazy_factory` entries from `registry.py`
3. Keep only generic reference adapters in `snowl/benchmarks/`: jsonl, csv
4. Update registry to rely entirely on entry-point discovery for non-reference benchmarks

## Not Yet Migrated

The following benchmarks remain in core (phase_3_heavy) and are not deprecated:

- AgentDojo
- AgentSafetyBench
- TerminalBench
- OSWorld
- ToolEmu
- ExploitBench

These require container provider interface stabilization before migration.

## Diagnostic Commands

```bash
# Check which benchmarks are shadowed
snowl bench doctor

# List all entries including shadowed plugins
snowl bench list --all
```
