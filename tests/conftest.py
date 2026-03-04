from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from snowl.core import get_default_tool_registry


@pytest.fixture(autouse=True)
def _reset_default_tool_registry():
    registry = get_default_tool_registry()
    registry.clear()
    yield
    registry.clear()
