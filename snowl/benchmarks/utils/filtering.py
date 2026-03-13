"""Shared utility module for benchmark adapters (filtering).

Framework role:
- Provides reusable dataset/split/filter/path/task helpers consumed by multiple adapters.

Runtime/usage wiring:
- Imported by concrete benchmark adapters to reduce duplicated plumbing code.
- Key top-level symbols in this file: `matches_filters`.

Change guardrails:
- Keep behavior generic; benchmark-specific rules belong in adapter packages.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


FilterResolver = Callable[[str], Any]
FilterComparator = Callable[[Any, Any], bool]


def matches_filters(
    *,
    filters: Mapping[str, Any],
    resolver: FilterResolver,
    stringify: bool = True,
    comparators: Mapping[str, FilterComparator] | None = None,
) -> bool:
    """Return True when all filters match values provided by ``resolver``."""
    comparators = comparators or {}
    for key, expected in filters.items():
        actual = resolver(key)
        comparator = comparators.get(key)
        if comparator is not None:
            if not comparator(actual, expected):
                return False
            continue
        if stringify:
            if str(actual) != str(expected):
                return False
            continue
        if actual != expected:
            return False
    return True
