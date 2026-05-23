# Repository Boundaries

## snowl (core)

The main `Qitor/snowl` repository contains:

- Core framework (`snowl/core/`) — agent protocols, tool abstractions, scoring contracts
- Runtime (`snowl/runtime/`) — container providers, policy engine
- Built-in benchmark adapters (`snowl/benchmarks/`) — currently includes all benchmarks
- CLI (`snowl/cli.py`) — `snowl bench list`, `snowl bench doctor`
- Model providers (`snowl/model/`)
- Agents (`snowl/agents/`)

## snowl-evals (external)

The `Qitor/snowl-evals` repository will contain:

- Benchmark adapter implementations
- Scorers and evaluation logic
- Manifest files (`benchmark.yaml`)
- Entry point registration functions
- Tests for adapters and entry points

### Dependency Direction

```
snowl-evals --> snowl (core)
```

- `snowl-evals` depends on `snowl` core for protocols, base classes, and registry
- `snowl` core must never import from `snowl-evals`
- `snowl` discovers `snowl-evals` via Python entry points at runtime

### What Stays in Core

These benchmarks remain in the main repository (phase_3_heavy):

- **AgentDojo** — agent+middleware evaluation with complex runtime
- **AgentSafetyBench** — agent safety with executor infrastructure
- **TerminalBench** — container-based terminal tasks
- **OSWorld** — OS-level container environments
- **ToolEmu** — tool emulation with external dependency
- **ExploitBench** — MCP-over-stdio container evaluation

These require heavy runtime infrastructure that is tightly coupled to the core
container provider system. They may be migrated in a future round after the
container provider interface is stabilized.

### Transition State (Current)

During the transition:

1. Built-in adapters in `snowl/benchmarks/<name>/` still work
2. `snowl-evals` plugin adapters register the same names via entry points
3. Built-in entries take precedence (canonical) when duplicates exist
4. Plugin duplicates are recorded as shadowed
5. `snowl.benchmarks.<name>` imports emit `DeprecationWarning`
6. After deprecation period, built-in adapters will be removed

### Import Rules

| Code Location | May Import | Must Not Import |
|---------------|-----------|-----------------|
| `snowl/core/` | stdlib, no third-party | `snowl.benchmarks`, `snowl.model`, `snowl.agents`, `snowl.scorer`, `snowl.runtime`, `snowl.tools` |
| `snowl/benchmarks/` | `snowl.core`, `snowl.model.base` | `snowl_evals` (unguarded) |
| `snowl_evals/` | `snowl.core`, `snowl.benchmarks.registry` (inside `register()` only) | `snowl.benchmarks.*` at module level |
