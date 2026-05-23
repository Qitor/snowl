# Plugin Contract for External Benchmark Packages

## Overview

External packages (such as `snowl-evals`) can register benchmark adapters with `snowl` through Python entry points. This allows `snowl bench list` and `snowl bench run <benchmark>` to discover and use adapters without modifying the core framework.

The official benchmark collection is [`snowl-evals`](https://github.com/Qitor/snowl-evals), a standalone package that lives outside the main snowl repository.

## Registration

### Package setup

In your package's `pyproject.toml`:

```toml
[project.entry-points."snowl.benchmarks"]
agentdojo = "snowl_evals.agentdojo:adapter"
terminalbench = "snowl_evals.terminalbench:adapter"
```

### Entry point target

The entry point must resolve to a callable that returns a `BenchmarkAdapter`-conforming object:

```python
# snowl_evals/agentdojo/__init__.py
from snowl.benchmarks.base import BenchmarkAdapter

def adapter(**kwargs) -> BenchmarkAdapter:
    from snowl_evals.agentdojo.adapter import AgentDojoAdapter
    return AgentDojoAdapter(**kwargs)
```

The callable receives `**kwargs` from the user (via CLI `--benchmark-args`) and must return an object satisfying the `BenchmarkAdapter` protocol:

- `.info` → `BenchmarkInfo`
- `.list_splits()` → `list[str]`
- `.load_tasks(*, split, limit, filters)` → `list[Task]`

## Discovery

`snowl` discovers plugins via `importlib.metadata.entry_points(group="snowl.benchmarks")`. Discovery happens:

- At registry initialization (when `get_default_benchmark_registry()` is first called)
- Plugin loading failures emit warnings, not crashes

## Usage

```bash
# Install core + benchmark collection
pip install snowl
pip install snowl-evals

# Or from local source for development:
pip install -e /path/to/snowl
pip install -e /path/to/snowl-evals

# List all available benchmarks (built-in + plugins)
snowl bench list

# Include shadowed plugin entries
snowl bench list --all

# Diagnose plugin installation
snowl bench doctor

# Run a plugin-provided benchmark
snowl bench run agentdojo --project project.yml
```

## Container providers

If a benchmark requires a custom container provider, register it via the `snowl.container_provider` entry point:

```toml
[project.entry-points."snowl.container_provider"]
osworld = "snowl_evals.osworld.provider:register_container_provider"
```

The entry point must resolve to a callable accepting a `ContainerProviderRegistry` that calls `registry.register(benchmark_name, provider_instance)`.

## Benchmark manifest

Each benchmark should include a `benchmark.yaml` manifest following the `snowl.benchmark_manifest.v1` schema. See `docs/schemas/README.md` for the schema definition.

## Compatibility

- External adapters must depend on `snowl>=0.1.0` (or the appropriate minimum version)
- Use `ChatModelClient` protocol from `snowl.model.base`, not concrete implementations
- Use `BaseBenchmarkAdapter` from `snowl.benchmarks.base_adapter` for row-oriented adapters
- Keep benchmark-specific imports out of `snowl.core`, `snowl.runtime`, and `snowl.tools`
