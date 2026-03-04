#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[snowl] cleaning previous build artifacts..."
rm -rf dist build *.egg-info

echo "[snowl] installing release tooling..."
python -m pip install -U build twine

echo "[snowl] building sdist and wheel..."
if ! python -m build; then
  echo "[snowl] standard isolated build failed, retrying with --no-isolation..."
  python -m build --no-isolation
fi

echo "[snowl] validating package metadata/rendering..."
python -m twine check dist/*

echo
echo "[snowl] build completed."
echo "Upload to TestPyPI:"
echo "  python -m twine upload --repository testpypi dist/*"
echo "Upload to PyPI:"
echo "  python -m twine upload dist/*"
