"""Path helpers for benchmark adapters."""

from __future__ import annotations

from pathlib import Path


def default_reference_path(anchor_file: str, *parts: str, parents: int = 3) -> str:
    root = Path(anchor_file).resolve().parents[parents]
    return str(root.joinpath("references", *parts))
