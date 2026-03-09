"""Task construction helpers for benchmark adapters."""

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
