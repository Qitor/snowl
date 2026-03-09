"""I/O helpers shared across benchmark adapters."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from snowl.errors import SnowlValidationError


def ensure_path_exists(path: str | Path, *, not_found_message: str) -> Path:
    resolved = Path(path)
    if not resolved.exists():
        raise SnowlValidationError(f"{not_found_message}: {resolved}")
    return resolved


def read_json_array(path: str | Path, *, not_found_message: str, invalid_message: str) -> list[Any]:
    resolved = ensure_path_exists(path, not_found_message=not_found_message)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SnowlValidationError(f"{invalid_message}: {resolved}")
    return list(data)


def read_json_object(path: str | Path, *, not_found_message: str, invalid_message: str) -> dict[str, Any]:
    resolved = ensure_path_exists(path, not_found_message=not_found_message)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SnowlValidationError(f"{invalid_message}: {resolved}")
    return dict(data)


def read_jsonl_rows(path: str | Path, *, not_found_message: str) -> list[dict[str, Any]]:
    resolved = ensure_path_exists(path, not_found_message=not_found_message)
    out: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            if isinstance(row, dict):
                out.append(dict(row))
    return out


def read_csv_rows(path: str | Path, *, not_found_message: str) -> list[dict[str, Any]]:
    resolved = ensure_path_exists(path, not_found_message=not_found_message)
    with resolved.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def read_yaml_mapping(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return dict(data)
