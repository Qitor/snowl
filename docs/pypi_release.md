# Snowl PyPI Release Guide

This project is now configured as a standard PyPI package (`snowl`) with PEP 517/621 metadata in `pyproject.toml`.

## 1) Build artifacts

From repo root:

```bash
cd /Users/morinop/coding/snowl_v2
python -m pip install -U build twine
python -m build
python -m twine check dist/*
```

Expected outputs:

- `dist/snowl-<version>.tar.gz`
- `dist/snowl-<version>-py3-none-any.whl`

## 2) Upload to TestPyPI (recommended)

```bash
python -m twine upload --repository testpypi dist/*
```

Or with token:

```bash
export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="<TEST_PYPI_TOKEN>"
python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
```

## 3) Upload to PyPI

```bash
export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="<PYPI_TOKEN>"
python -m twine upload dist/*
```

## 4) Verify install

```bash
pip install -U snowl
snowl --help
```

## 5) Version bump checklist

Before each release:

1. Update version in:
- `snowl/__init__.py`
- `pyproject.toml`
2. Rebuild:
- `rm -rf dist build *.egg-info`
- `python -m build`
3. Run checks:
- `python -m twine check dist/*`

## 6) GitHub Actions auto publish

Workflow file:

- `.github/workflows/pypi-publish.yml`

Trigger rules:

- release published -> publish to PyPI
- manual dispatch -> publish to PyPI

Required repository secrets:

- `PYPI_API_TOKEN`

Release example:

```bash
# create/publish a GitHub Release for version v0.1.1
```

## Notes

- Package name is `snowl`.
- Console entry point is `snowl = snowl.cli:main`.
- UI panel config files are included in wheel via package data settings.
