# Development Guide

Setting up the Snowl development environment, coding conventions, and contribution workflow.

---

## Setup

```bash
# Clone and install with dev dependencies
git clone https://github.com/Qitor/snowl.git
cd snowl
pip install -e ".[dev]"

# Install snowl-evals alongside (for integration testing)
cd ../snowl-evals
pip install -e ".[dev]"

# Verify installation
python -c "from snowl import quick_eval; print('OK')"
python -m snowl.check
```

## Project Structure

```
snowl/
├── core/           # Contracts — no third-party imports, no adapter imports
├── agents/         # Agent implementations (ReActAgent, ChatAgent)
├── adapters/       # Framework adapters (QitOS, LangGraph, OpenAI Agents)
├── benchmarks/     # Benchmark adapters (each a sub-package)
├── scorer/         # 15+ scorer implementations
├── model/          # ChatModelClient protocol + OpenAI client
├── runtime/        # Trial execution engine, scheduler, policy
├── tools/          # ToolMiddleware, StatefulToolExecutor, EmulatedTool
├── cli.py          # CLI entry point
├── dispatch.py     # Eval orchestration
└── eval/           # Eval run bootstrap
```

## Architecture Rules

- **Core** (`snowl/core/`) must stay framework-independent. No third-party imports, no adapter imports.
- **Adapters depend on core, never the reverse.** If core imports from `snowl.benchmarks`, `snowl.model`, etc., that is a boundary violation.
- **New integrations must be added as adapters.** Benchmark adapters go in `snowl/benchmarks/`. Model providers go in `snowl/model/`.
- **Public APIs require tests and docs.** Anything re-exported from `snowl.core` or `snowl/__init__.py` is a public API.

See `CLAUDE.md` and `docs/governance.md` for the full boundary rules.

## Coding Conventions

- **Type annotations**: Use Python 3.10+ syntax (`list[str]`, `str | None`, etc.).
- **Dataclasses**: Prefer `@dataclass(frozen=True)` for value objects.
- **Protocols**: Use `typing.Protocol` for interfaces that adapters implement.
- **Error types**: Raise `SnowlValidationError` for user-facing errors.
- **Docstrings**: Module-level docstring with Framework role / Runtime wiring / Change guardrails sections (see existing modules for examples).
- **Imports**: Deferred imports (`from snowl.benchmarks.registry import ...` inside functions) are acceptable for breaking circular dependencies, but direct imports at module level from core to adapters are forbidden.

## Running Tests

```bash
pytest tests/ -q                    # Full suite
pytest tests/test_scorer_contracts.py -v  # Specific file
pytest tests/ -q -m "not live"      # Skip live tests
```

See [testing.md](./testing.md) for detailed test categories and conventions.

## Creating a New Benchmark Adapter

1. Create `snowl/benchmarks/<name>/` with `adapter.py` subclassing `BaseBenchmarkAdapter`
2. Implement template methods: `_iter_rows`, `_row_split`, `_row_to_sample`
3. Register in `snowl/benchmarks/registry.py` via `register_builtin_benchmarks()`
4. Add tests in `tests/test_<name>_benchmark.py`

See [custom-benchmark-adapter.md](./how-to/custom-benchmark-adapter.md) for a walkthrough.

## Creating a New Scorer

1. Create a class implementing the `Scorer` protocol (`score()` method returning `dict[str, Score]`)
2. Place in `snowl/scorer/` or a benchmark-specific module
3. Add to `snowl/scorer/__init__.py` if it's a general-purpose scorer
4. Add tests verifying scoring logic

## Pre-commit Checks

Before pushing, verify:

```bash
pytest tests/ -q
python -c "from snowl import quick_eval"
grep -r 'sk-' examples/  # No leaked secrets
```
