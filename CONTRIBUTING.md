# Contributing to Snowl

Thank you for your interest in contributing to Snowl! This guide covers the essentials for making effective contributions.

## Architecture: Core vs. Adapters

Snowl follows a **core-first architecture**:

- **Core layer** (`snowl/core/`): Defines stable contracts (Task, Agent, Scorer, ToolSpec, EnvSpec, TaskResult) with zero third-party dependencies and zero imports from adapter layers.
- **Adapter layer**: Everything else — benchmark adapters, model clients, agent implementations, scorers, runtime, CLI, UI.

**Key rules:**
- Adapters may depend on core, but core must **never** depend on adapters.
- New integrations (benchmarks, providers, frameworks) must be added as adapters, not by modifying core.
- Public APIs (re-exported from `snowl.core`) require tests and documentation.

## Getting Started

1. Fork and clone the repository
2. Install with dev dependencies: `pip install -e ".[dev]"`
3. Run the test suite: `pytest tests/ -q`
4. Read [ARCHITECTURE.md](./ARCHITECTURE.md) for system overview

## Development Workflow

1. Create a feature branch from `main`
2. Make changes with clear, focused commits
3. Add or update tests for your changes
4. Ensure all tests pass: `pytest tests/ -q`
5. Run the architecture boundary test: `pytest tests/test_architecture_boundaries.py -v`
6. Open a pull request

## Adding a New Benchmark Adapter

**Do not add a new third-party benchmark directly to `snowl/benchmarks/` by
default.** Third-party benchmark integrations should live outside the main
repository and register through the plugin contract. The main repository should
only contain:

- tiny reference adapters (generic JSONL/CSV)
- conformance fixtures
- minimal examples needed to test framework behavior

### Recommended path: external adapter package

1. Create a standalone package (e.g., `snowl-evals-mybench`) with a
   `BenchmarkAdapter` subclass
2. Register via Python entry point in your `pyproject.toml`:

   ```toml
   [project.entry-points."snowl.benchmarks"]
   mybench = "snowl_evals_mybench:register"
   ```

3. Include a benchmark manifest (`benchmark.yaml`) following the
   `snowl.benchmark_manifest.v1` schema
4. Run conformance: `snowl bench check mybench`
5. Users install: `pip install snowl snowl-evals-mybench`

See [docs/governance/plugin_contract.md](./docs/governance/plugin_contract.md)
for the full plugin registration guide.

### If a benchmark is accepted into the main repository

1. Create `snowl/benchmarks/<name>/` with `adapter.py` subclassing `BaseBenchmarkAdapter`
2. Implement `_iter_rows`, `_row_split`, `_row_to_sample`
3. Optionally add `agent.py`, `scorer.py`, `executor.py`
4. Register in `snowl/benchmarks/registry.py` using `_lazy_factory`
5. Add a benchmark manifest (`benchmark.yaml`) next to the adapter
6. Add tests in `tests/test_<name>_benchmark.py`
7. Add example project in `examples/<name>/`

### Benchmark Adapter Checklist

- [ ] Adapter lives outside core unless explicitly accepted as reference adapter
- [ ] Manifest included (`benchmark.yaml` following `snowl.benchmark_manifest.v1`)
- [ ] Source / paper / code / dataset links included in manifest
- [ ] License notes included in manifest
- [ ] Runtime requirements declared in manifest
- [ ] Scoring method documented in manifest
- [ ] Sample fixture included
- [ ] Conformance test passes (`snowl bench check <name>`)
- [ ] Heavy dependencies are optional (use `pyproject.toml` extras)

## Adding a New Scorer

1. Create scorer in `snowl/scorer/` implementing the `Scorer` protocol from `snowl.core`
2. If the scorer needs a model client, depend on the `ChatModelClient` **protocol** (not a concrete implementation)
3. Add to `snowl/scorer/__init__.py` exports
4. Add tests with mock transport (no real API calls)

## Code Style

- Follow existing patterns in the codebase
- Use type hints on public APIs
- Add module docstrings with framework role and change guardrails
- Keep benchmark-specific assumptions out of shared code

## Testing

- Core tests must import only from `snowl.core` and stdlib
- Adapter tests should use `tmp_path` for test data and `httpx.MockTransport` for model calls
- No real API keys or network access in tests
- All tests must pass: `pytest tests/ -q`

## Pull Request Checklist

- [ ] Tests pass locally
- [ ] Core boundary test passes
- [ ] No leaked secrets or API keys
- [ ] Public API changes are documented
- [ ] New adapters don't modify core contracts
