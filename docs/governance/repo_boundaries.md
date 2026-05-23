# Repository Boundaries

## What belongs in `snowl`

`snowl` is the core agent evaluation framework. It contains:

- **Core evaluation abstractions** — `snowl/core/`: Agent, Task, Scorer, Tool, EnvSpec protocols and data classes
- **Runtime execution engine** — `snowl/runtime/`: trial lifecycle, container management, sandbox, scheduling
- **Artifact schema and event protocol** — `snowl/aggregator/`, `snowl/observability/`
- **Project/suite config loading** — `snowl/project_config.py`, `snowl/suite.py`
- **CLI** — `snowl/cli.py`
- **Provider abstraction** — `snowl/model/`, `snowl/envs/`, `snowl/adapters/`
- **Generic reference adapters** — `snowl/benchmarks/csv_adapter.py`, `jsonl_adapter.py`, `example_task.py`
- **Web monitor integration** — `snowl/web/`, `webui/`
- **Conformance test utilities** — `snowl/benchmarks/conformance.py`
- **Generic scorer strategies** — `snowl/scorer/`
- **Tool middleware** — `snowl/tools/`
- **Reporting and export** — `snowl/report/`, `snowl/export/`

## What should NOT keep accumulating in `snowl`

- Large third-party benchmark integrations (AgentDojo, ToolEmu, OSWorld, etc.)
- Benchmark-specific heavy dependencies (`mcp`, `beautifulsoup4`, `easyocr`, etc.)
- Benchmark-specific datasets or cache files
- Benchmark-specific Docker/runtime configurations
- One-off reproduction scripts
- Benchmark-specific reports or analysis

## What should live in `snowl-evals` (planned)

- Official third-party benchmark adapters
- Benchmark manifests (`benchmark.yaml`)
- Benchmark-specific dependencies (as optional extras)
- Benchmark examples
- Benchmark-specific tests and fixtures
- Source/citation/license metadata per benchmark

## What should live in `snowl-recipes` (future)

- Tutorial projects
- Runnable experiment suites
- Model comparison recipes
- Reproduction reports
- Notebooks
- Opinionated configurations

## Boundary rules

1. **Core must stay framework-independent.** No third-party imports in `snowl/core/`.
2. **Adapters depend on core, never the reverse.** Core must not import from `snowl.benchmarks/*`, `snowl.agents`, `snowl.model`, etc.
3. **Runtime must not hard-import benchmark code.** Use lazy imports in provider bridges only.
4. **New benchmark integrations should use the plugin contract** and live outside `snowl` by default.
5. **Heavy dependencies must be optional.** Use `[extras]` in `pyproject.toml`.
6. **Container providers register via bridge functions**, not direct imports from runtime.
