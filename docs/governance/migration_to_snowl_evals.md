# Migration Plan: snowl → snowl-evals

This document describes the planned migration of third-party benchmark adapters
from the `snowl` core repository into a separate `snowl-evals` package.

## Current State (Phase 1)

- All built-in benchmark adapters live inside `snowl/benchmarks/`.
- The registry uses `_lazy_factory()` to defer adapter imports until first use.
- Plugin discovery via `importlib.metadata.entry_points` is wired and tested.
- Benchmark manifest schema (`snowl.benchmark_manifest.v1`) is established.
- Two reference manifests exist: `jsonl` and `strongreject`.

**No user-visible changes in Phase 1.** All existing CLI commands and Python
APIs continue to work identically.

## Phase 2: Create `snowl-evals` and Migrate Simple Adapters

Create the `snowl-evals` package with entry-point registration, then migrate
simple row-oriented benchmarks (no containers, no heavy dependencies).

**Scope**: StrongReject, WMDP, BFCL, XSTest, MASK, SecQA, SevenLLM,
CyberMetric, CoConot, Fortress, IPI Coding Agent, AgentBench-OS, AgentHarm.

**Steps per benchmark**:
1. Move `snowl/benchmarks/<name>/` → `snowl_evals/<name>/`
2. Move `benchmark.yaml` manifest alongside adapter
3. Add entry point in `snowl-evals` pyproject.toml:
   ```toml
   [project.entry-points."snowl.benchmarks"]
   strongreject = "snowl_evals.strongreject:register"
   ```
4. Add compatibility shim in `snowl/benchmarks/<name>/__init__.py` that imports
   from `snowl_evals.<name>` with a deprecation warning
5. Move benchmark-specific tests to `snowl-evals/tests/`
6. Update registry.py to remove the `_lazy_factory` entry for migrated adapters

**Compatibility shim pattern**:
```python
# snowl/benchmarks/strongreject/__init__.py
import warnings
warnings.warn(
    "Importing from snowl.benchmarks.strongreject is deprecated. "
    "Install snowl-evals and import from snowl_evals.strongreject instead.",
    DeprecationWarning,
    stacklevel=2,
)
from snowl_evals.strongreject import *  # noqa: F401,F403
```

## Phase 3: Migrate Heavy Environment Benchmarks

Migrate container-backed and dependency-heavy benchmarks.

**Scope**: AgentDojo, ToolEmu, AgentSafetyBench, TerminalBench, OSWorld,
ExploitBench.

**Additional steps**:
1. Container providers move to `snowl_evals/providers/`
2. `snowl/runtime/container_providers.py` keeps the lazy import bridge with
   deprecation warning
3. Heavy optional dependencies (`mcp`, `emulation`, etc.) become deps of
   `snowl-evals[<name>]` extras rather than `snowl[<name>]`

## Phase 4: Remove Compatibility Shims

After at least 2 minor releases with deprecation warnings:

1. Remove `snowl/benchmarks/<name>/` directories for all migrated benchmarks
2. Remove `_lazy_factory` entries from registry.py
3. Keep only reference adapters in `snowl/benchmarks/`: `jsonl`, `csv`,
   `example_task`, `external`
4. Update registry to rely entirely on entry-point discovery for non-reference
   benchmarks

## Proposed `snowl-evals` Repository Structure

```
snowl-evals/
  pyproject.toml
  README.md
  CHANGELOG.md
  snowl_evals/
    __init__.py
    registry.py              # register() function for entry-point wiring
    agentdojo/
      benchmark.yaml
      adapter.py
      agent.py
      scorer.py
      README.md
      tests/
    terminalbench/
      benchmark.yaml
      adapter.py
      provider.py
      tests/
    osworld/
    toolemu/
    strongreject/
    wmdp/
    ...
  examples/
  tests/
  docs/
```

## Entry Point Contract

`snowl-evals` registers all its adapters via:

```toml
[project.entry-points."snowl.benchmarks"]
agentdojo = "snowl_evals.agentdojo:register"
terminalbench = "snowl_evals.terminalbench:register"
# ...
```

Each `register(registry)` function calls `registry.register(name, info, factory)`.

Users install:
```bash
pip install snowl
pip install snowl-evals[agentdojo,terminalbench]
snowl bench list      # shows all registered benchmarks
snowl bench run agentdojo --project project.yml
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Users break on import paths | Compatibility shims with DeprecationWarning for 2 releases |
| Plugin discovery fails silently | Registry warns on broken entry points; `bench list` shows what loaded |
| Container provider bridge breaks | Lazy import with try/except already in place; add deprecation path |
| Performance regression from entry points | `_lazy_factory` already defers heavy imports; no change in latency |

## Phase 2 Status: COMPLETE

All 13 phase_2_simple benchmarks are migrated into `snowl-evals` (formerly `external/snowl-evals-prototype/`):

- strongreject, xstest, wmdp, sec_qa, cybermetric (Round 2)
- coconot, mask, sevenllm, fortress, agentharm, agent_bench_os, bfcl, ipi_coding_agent (Round 3)

Compatibility shims with `DeprecationWarning` are in place for all 13 benchmarks.
Duplicate plugin handling is hardened: built-in wins, plugin shadowed, doctor reports.
All tests pass: 698 snowl, 104 snowl-evals.

## Phase 4 Status: COMPLETE

- `external/snowl-evals-prototype/` extracted to standalone `../snowl-evals/` package
- Version: 0.1.0.dev0 (pre-release)
- 104 snowl-evals tests pass
- Cross-repo integration script added: `scripts/check_snowl_evals_integration.sh`
- Prototype removed from snowl repository
- Deprecation policy documented

## Phase 3: Not Started

Heavy/runtime benchmarks remain in core:
- AgentDojo, ToolEmu, AgentSafetyBench, TerminalBench, OSWorld, ExploitBench

These require container provider interface stabilization before migration.

## Publishing Plan

1. Create `Qitor/snowl-evals` repository on GitHub
2. Push local `../snowl-evals/` to remote
3. Activate CI (`.github/workflows/ci.yml` skeleton already exists)
4. TestPyPI dry run
5. Publish to PyPI
6. Remove built-in adapter code from snowl after 2 minor releases with deprecation warnings
