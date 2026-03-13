"""Shared utility module for benchmark adapters (paths).

Framework role:
- Provides reusable dataset/split/filter/path/task helpers consumed by multiple adapters.

Runtime/usage wiring:
- Imported by concrete benchmark adapters to reduce duplicated plumbing code.
- Key top-level symbols in this file: `default_reference_path`.

Change guardrails:
- Keep behavior generic; benchmark-specific rules belong in adapter packages.
"""

from __future__ import annotations

from pathlib import Path


def default_reference_path(anchor_file: str, *parts: str, parents: int = 3) -> str:
    root = Path(anchor_file).resolve().parents[parents]
    return str(root.joinpath("references", *parts))
