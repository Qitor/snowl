# Release Process

How to publish Snowl and snowl-evals to PyPI.

---

## Version Bumping

1. Update `__version__` in `snowl/__init__.py` and `snowl_evals/__init__.py`
2. Update `CHANGELOG.md` — move items from `## Unreleased` to `## vX.Y.Z` with date
3. Commit with message `bump version to X.Y.Z`

## Publishing to PyPI

```bash
# Build distributions
python -m build

# Upload to TestPyPI (optional verification)
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

## Pre-release Checklist

- [ ] All tests pass: `pytest tests/ -q`
- [ ] Architecture boundary test passes: `pytest tests/test_architecture_boundaries.py -v`
- [ ] No leaked secrets: `grep -r 'sk-' examples/`
- [ ] `python -c "from snowl import quick_eval"` works
- [ ] `python -m snowl.check` reports healthy
- [ ] `CHANGELOG.md` updated with release date
- [ ] Version bumped in `__init__.py`
- [ ] Git tag created: `git tag vX.Y.Z`

## snowl-evals Release

Follow the same process in the `snowl-evals` repository. snowl-evals version numbers are independent.

## Hotfix Process

1. Create a `hotfix/X.Y.Z+1` branch from the release tag
2. Apply the fix with a test
3. Bump patch version
4. Follow the pre-release checklist
5. Merge back to main

## Deprecation Cycle

When removing a public API:

1. **vX.Y.0**: Add `DeprecationWarning` with removal version
2. **vX.(Y+1).0**: Keep the deprecated API with warning
3. **vX.(Y+2).0** or later: Remove the API

Example:
```python
import warnings
warnings.warn(
    "snowl.quick_eval_legacy() is deprecated since v0.2.0 and will be removed in v0.3.0. "
    "Use quick_eval() instead.",
    DeprecationWarning,
    stacklevel=2,
)
```
