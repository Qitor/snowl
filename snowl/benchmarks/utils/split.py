"""Split normalization helpers."""

from __future__ import annotations


def normalize_split(raw: object, default_split: str) -> str:
    text = str(raw or "").strip()
    return text or default_split
