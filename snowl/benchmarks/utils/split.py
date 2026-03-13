"""Shared utility module for benchmark adapters (split).

Framework role:
- Provides reusable dataset/split/filter/path/task helpers consumed by multiple adapters.

Runtime/usage wiring:
- Imported by concrete benchmark adapters to reduce duplicated plumbing code.
- Key top-level symbols in this file: `normalize_split`.

Change guardrails:
- Keep behavior generic; benchmark-specific rules belong in adapter packages.
"""

from __future__ import annotations


def normalize_split(raw: object, default_split: str) -> str:
    text = str(raw or "").strip()
    return text or default_split
