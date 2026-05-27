# Testing

How Snowl tests are organized, how to run them, and how to write new ones.

---

## Running Tests

```bash
# Full suite
pytest tests/ -q

# Specific test file
pytest tests/test_scorer_contracts.py -v

# Architecture boundary test
pytest tests/test_architecture_boundaries.py -v

# Skip live tests (require API keys)
pytest tests/ -q -m "not live"
```

## Test Categories

| Category | Location | Purpose |
|----------|----------|---------|
| Core contracts | `tests/test_*_contracts.py` | Validate `Task`, `Agent`, `Scorer`, `ToolSpec` protocols |
| Benchmark adapters | `tests/test_*_benchmark.py` | Registry presence, conformance, determinism, scorer logic |
| Runtime engine | `tests/test_runtime_*.py` | Trial lifecycle, middleware, budget resolution |
| Scorers | `tests/test_*scorer*.py` | Scoring logic, judge templates, cost normalization |
| Architecture boundaries | `tests/test_architecture_boundaries.py` | Core never imports adapters |
| CLI | `tests/test_cli_*.py` | Subcommand dispatch, validation |
| Live (requires API keys) | `tests/e2e_live/` | End-to-end against real models |

## Writing Core Tests

Core tests must:
- Use only `snowl.core` imports and stdlib
- Never import from `snowl.agents`, `snowl.model`, `snowl.benchmarks`, `snowl.runtime`
- Use pure dataclass/protocol instances, no mocking of adapters
- Validate contracts, not implementation details

```python
from snowl.core import Task, EnvSpec

def test_task_requires_id():
    task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([]))
    assert task.task_id == "t1"
```

## Writing Adapter Tests

Adapter tests should:
- Use `tmp_path` for test datasets (not real reference corpora)
- Mock `ChatModelClient.generate()` with `httpx.MockTransport` for model-dependent tests
- Verify: registry presence, conformance, sample determinism, scorer logic
- Never require real API keys or network access

```python
def test_benchmark_in_registry():
    from snowl.benchmarks.registry import get_default_benchmark_registry
    registry = get_default_benchmark_registry()
    names = [e.info.name for e in registry.list()]
    assert "strongreject" in names
```

## Writing Architecture Boundary Tests

The boundary test at `tests/test_architecture_boundaries.py` verifies that `snowl/core/` never imports from adapter packages. If you add a new module to core, ensure it has no adapter imports.

```bash
# Verify no violations
python -c "
import importlib, pkgutil
from pathlib import Path
core = Path('snowl/core')
for _, name, _ in pkgutil.iter_modules([str(core)]):
    src = (core / f'{name}.py').read_text()
    for pkg in ['snowl.agents', 'snowl.model', 'snowl.benchmarks', 'snowl.scorer', 'snowl.runtime', 'snowl.tools']:
        if pkg in src:
            print(f'VIOLATION: snowl.core.{name} -> {pkg}')
"
```

## CI Integration

Tests run on every push via GitHub Actions. The CI pipeline:
1. Runs `pytest tests/ -q -m "not live"` (no API keys in CI)
2. Runs architecture boundary test
3. Checks for leaked secrets (`grep -r 'sk-' examples/`)
4. Validates `python -c "from snowl import quick_eval"`
