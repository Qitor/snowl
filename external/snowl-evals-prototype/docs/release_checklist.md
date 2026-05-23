# Release Checklist

Pre-release verification steps for snowl-evals.

## Before Release

- [ ] All adapter imports work without errors
- [ ] All entry points are valid (`snowl bench doctor`)
- [ ] All manifests validate
- [ ] All tests pass (`pytest tests/ -q`)
- [ ] No circular imports when installed alongside snowl
- [ ] No dependency on `snowl.benchmarks.*` at module level (only inside `register()`)
- [ ] README and CHANGELOG are up to date
- [ ] Version in `pyproject.toml` is bumped

## Extraction Steps

1. Copy `external/snowl-evals-prototype/` to standalone repo
2. Update `pyproject.toml` to depend on released `snowl` version (not editable)
3. Set up CI (use `.github/workflows/ci.yml` skeleton)
4. Update README paths (remove `/path/to/snowl` references)
5. Push to `Qitor/snowl-evals`
6. Publish to PyPI

## Post-Release

- [ ] Verify `pip install snowl-evals` works
- [ ] Verify entry points are discovered by snowl
- [ ] Verify `snowl bench list` shows plugin benchmarks
- [ ] Verify `snowl bench doctor` reports no issues
- [ ] Update snowl core to add deprecation shims for migrated benchmarks
- [ ] Plan removal of built-in adapter code after deprecation period
