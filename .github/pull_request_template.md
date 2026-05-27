## Summary

<!-- 1-3 bullet points describing the change -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Refactor (no functional change)
- [ ] Documentation

## Checklist

- [ ] Tests pass: `pytest tests/ -q`
- [ ] Architecture boundary test passes: `pytest tests/test_architecture_boundaries.py -v`
- [ ] No leaked secrets: `grep -r 'sk-' examples/`
- [ ] Public API changes are reflected in `snowl/__init__.py` and `docs/public_api.md`
- [ ] No core -> adapter boundary violations (core must not import from adapters, benchmarks, model, runtime, scorer, or tools)

## Core/Adapter Boundary

If this PR touches `snowl/core/`, confirm:
- [ ] No new imports from `snowl.agents`, `snowl.model`, `snowl.benchmarks`, `snowl.scorer`, `snowl.runtime`, or `snowl.tools`
- [ ] No third-party imports added to core modules
