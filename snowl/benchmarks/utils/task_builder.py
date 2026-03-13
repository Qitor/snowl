"""Shared utility module for benchmark adapters (task_builder).

Framework role:
- Provides reusable dataset/split/filter/path/task helpers consumed by multiple adapters.

Runtime/usage wiring:
- Imported by concrete benchmark adapters to reduce duplicated plumbing code.
- Key top-level symbols in this file: `build_benchmark_task`.

Change guardrails:
- Keep behavior generic; benchmark-specific rules belong in adapter packages.
"""

from __future__ import annotations

from typing import Any

from snowl.core import EnvSpec, Task


def build_benchmark_task(
    *,
    benchmark: str,
    split: str,
    samples: list[dict[str, Any]],
    env_spec: EnvSpec,
    metadata: dict[str, Any],
) -> Task:
    return Task(
        task_id=f"{benchmark}:{split}",
        env_spec=env_spec,
        sample_iter_factory=lambda: iter(samples),
        metadata=dict(metadata),
    )
