#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
if ! python -m pip install --no-build-isolation -e ".[dev]"; then
  echo "pip editable install failed, fallback to setup.py develop..."
  python setup.py develop
fi

echo "Snowl installed in editable mode (venv: $VENV_DIR)."
echo "Activate with: source $VENV_DIR/bin/activate"
echo "Try: snowl --help"
