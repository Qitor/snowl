# Development Guide — Snowl

---

## Install

```bash
# Clone and install in editable mode
git clone https://github.com/Qitor/snowl.git
cd snowl
pip install -e .

# With dev dependencies (if configured)
pip install -e ".[dev]"
```

## Test

```bash
# Full test suite (fast, no network required)
pytest tests/ -q

# Architecture boundary tests
pytest tests/test_architecture_boundaries.py -v

# Core contract tests only
pytest tests/test_task_contracts.py tests/test_scorer_contracts.py tests/test_agent_contracts.py -v

# Specific benchmark smoke tests
pytest tests/test_strongreject_benchmark.py tests/test_terminalbench_benchmark.py -v

# Runtime engine tests
pytest tests/test_runtime_engine.py tests/test_resource_scheduler.py -v

# Skip slow/integration tests
pytest tests/ -q -m "not slow"
```

## Architecture Boundary Checks

```bash
# Automated boundary tests (core isolation, runtime → benchmark, public API, secret hygiene)
pytest tests/test_architecture_boundaries.py -v

# Manual core boundary check (no forbidden imports)
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

## WebUI Typecheck

```bash
cd webui
npm install
npm run -s typecheck
```

If `node_modules` are not installed, the typecheck will fail. Install first.

## Secret Scanning

```bash
# Check for leaked API keys in examples and docs
grep -R "sk-" examples docs README.md README.zh-CN.md pyproject.toml setup.py || true

# Check for internal proxy URLs
grep -R "openapi-.*\.sii\.edu\.cn" examples/ --include='*.yml' --include='*.py' || true
grep -R "dsv3\.sii\.edu\.cn" examples/ --include='*.yml' --include='*.py' || true

# Automated check (part of test_architecture_boundaries.py)
pytest tests/test_architecture_boundaries.py::TestExampleSecretHygiene -v
```

Rules for example `project.yml` files:
- Use `${OPENAI_API_KEY}`, `${SNOWL_SMOKE_API_KEY}`, or similar env var placeholders
- `sk-...` is acceptable as a placeholder indicator (not a real key)
- `unused` or `unused-env-read-by-example-code` are acceptable for smoke tests
- Never commit real API keys, base URLs for internal proxies, or encrypted key strings

## Benchmark Smoke Test

```bash
# List available benchmarks
snowl bench list

# Scaffold a new benchmark
snowl bench scaffold mybench --out ./mybench

# Validate a benchmark adapter
snowl bench check mybench --adapter ./mybench/adapter.py:adapter --adapter-arg dataset_path=./mybench/data.jsonl
```

## Compile Check

```bash
python -m compileall snowl tests
```

## Release Hygiene Checklist

Before a release:

1. All tests pass: `pytest tests/ -q`
2. Architecture boundary tests pass: `pytest tests/test_architecture_boundaries.py -v`
3. WebUI typecheck passes: `cd webui && npm run -s typecheck`
4. No leaked secrets: `grep -R "sk-" examples/ --include='*.yml'` returns only `sk-...` placeholders
5. No internal proxy URLs: `grep -R "sii.edu.cn" examples/ --include='*.yml' --include='*.py'`
6. Compile check passes: `python -m compileall snowl tests`
7. `__version__` updated in `snowl/__init__.py`
8. CHANGELOG updated
9. No planning/progress markdown files at repo root
10. No build artifacts committed (site/, .next/, .egg-info/, docs.zip)
