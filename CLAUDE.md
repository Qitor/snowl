# CLAUDE.md — AI Agent Governance for Snowl

## Core Architecture Rules

- **Core layer** (`snowl/core/`) must stay framework-independent. No third-party imports, no adapter imports.
- **Adapters depend on core, never the reverse.** If you find core importing from `snowl.benchmarks`, `snowl.model`, `snowl.agents`, `snowl.scorer`, `snowl.runtime`, or `snowl.tools`, that is a boundary violation.
- **New integrations must be added as adapters.** Benchmark adapters go in `snowl/benchmarks/`. Model providers go in `snowl/model/`. Do not modify core contracts to accommodate a specific integration.
- **Public APIs require tests and docs.** Anything re-exported from `snowl.core` or `snowl/__init__.py` is a public API. Changes must have regression tests.

## Adapter-Specific Rules

- Adapter-specific assumptions must not leak into core or shared code.
- Benchmark-specific field names, score keys, and container logic belong in `snowl/benchmarks/<name>/`, not in `snowl/runtime/` or `snowl/tools/`.
- Use the `ChatModelClient` protocol (`snowl.model.base.ChatModelClient`) rather than `OpenAICompatibleChatClient` in type annotations for agents and tools.

## Refactoring Rules

- Every refactor must preserve behavior and run validation (`pytest tests/ -q`).
- Do not change public APIs without regression tests.
- Do not perform broad speculative rewrites.
- Keep diffs reviewable — prefer small, well-documented improvements.

## Validation Commands

```bash
# Full test suite
pytest tests/ -q

# Architecture boundary test
pytest tests/test_architecture_boundaries.py -v

# No leaked secrets
grep -r 'sk-' examples/

# Core boundary check
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

## Repository Cleanliness

- No plan/task/progress markdown files on GitHub
- No API keys or secrets in committed files
- No build artifacts (site/, .next/, .egg-info/, docs.zip) in git
- Internal planning files (PLANS.md, next_version.md, AGENTS.md) are gitignored
