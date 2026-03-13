"""Small helper layer for loading one benchmark task and env-driven sample limits.

Framework role:
- Provides convenience wrappers used by examples/tests to avoid repeating split/limit/filter plumbing.

Runtime/usage wiring:
- Bridges environment-variable overrides to adapter loading calls (`load_tasks`).

Change guardrails:
- Keep helpers thin; benchmark semantics should stay in adapters, not in this utility module.
"""

from __future__ import annotations

from typing import Any

from snowl.benchmarks.base import BenchmarkAdapter
from snowl.core import Task
from snowl.utils.env import env_optional_int, env_split, env_str


def load_single_task(
    adapter: BenchmarkAdapter,
    *,
    split: str,
    limit: int | None = None,
    filters: dict[str, Any] | None = None,
) -> Task:
    return adapter.load_tasks(split=split, limit=limit, filters=filters)[0]


def env_task_split(name: str, default: str) -> str:
    return env_split(name, default)


def env_task_limit(name: str) -> int | None:
    return env_optional_int(name)


def env_task_sample_limit(name: str, *, default: int) -> int | None:
    raw = env_str(name, str(default))
    if not raw or raw.lower() in {"none", "all", "-1"}:
        return None
    try:
        return max(1, int(raw))
    except Exception:
        return default
