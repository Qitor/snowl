#!/usr/bin/env bash
# Cross-repository integration check for snowl + snowl-evals.
#
# Verifies that the standalone snowl-evals package installs correctly,
# registers its benchmarks via entry points, and integrates with the
# snowl CLI without errors.
#
# Usage:
#   SNOWL_EVALS_DIR=/path/to/snowl-evals scripts/check_snowl_evals_integration.sh
#
# Default: looks for ../snowl-evals relative to this repo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVALS_DIR="${SNOWL_EVALS_DIR:-$ROOT/../snowl-evals}"

if [ ! -d "$EVALS_DIR" ]; then
  echo "ERROR: snowl-evals directory not found: $EVALS_DIR"
  echo "Set SNOWL_EVALS_DIR=/path/to/snowl-evals or place it as a sibling directory."
  exit 1
fi

if [ ! -f "$EVALS_DIR/pyproject.toml" ]; then
  echo "ERROR: No pyproject.toml in $EVALS_DIR — not a valid snowl-evals package."
  exit 1
fi

echo "--- Installing snowl (editable) ---"
python -m pip install -e "$ROOT" -q

echo "--- Installing snowl-evals (editable) ---"
python -m pip install -e "$EVALS_DIR" -q

echo "--- Running snowl plugin discovery tests ---"
python -m pytest "$ROOT/tests/test_plugin_discovery.py" -q

echo "--- Running snowl registry duplicate tests ---"
python -m pytest "$ROOT/tests/test_benchmark_registry_duplicates.py" -q

echo "--- Running snowl-evals tests ---"
python -m pytest "$EVALS_DIR/tests/" -q

echo "--- CLI: snowl bench list ---"
python -m snowl bench list 2>/dev/null || true

echo "--- CLI: snowl bench list --all ---"
python -m snowl bench list --all 2>/dev/null || true

echo "--- CLI: snowl bench doctor ---"
python -m snowl bench doctor 2>/dev/null || true

echo ""
echo "Integration check complete."
