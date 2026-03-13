"""Environment-variable parsing helpers with consistent coercion semantics.

Framework role:
- Centralizes string/int/float/bool parsing so adapters and CLI helpers do not duplicate env handling.

Runtime/usage wiring:
- Used by benchmark helpers and config plumbing where lightweight env overrides are supported.

Change guardrails:
- Keep coercion behavior predictable; changes here can silently alter benchmark selection/limits.
"""

from __future__ import annotations

import os


def env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


def env_split(name: str, default: str) -> str:
    value = env_str(name, default)
    return value or default


def env_optional_int(name: str) -> int | None:
    raw = env_str(name)
    if not raw:
        return None
    return int(raw)


def env_int(name: str, default: int) -> int:
    return int(env_str(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env_str(name, str(default)))


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}
