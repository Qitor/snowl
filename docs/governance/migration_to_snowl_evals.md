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

## Not Started

The following items are deferred until `snowl-evals` repository creation:
- Actual code migration
- CI pipeline for `snowl-evals`
- Package publishing workflow
- Documentation cross-links
