from __future__ import annotations

import os
from pathlib import Path

from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "OSWorld" / "evaluation_examples"


def _sample_limit() -> int | None:
    raw = str(os.getenv("SNOWL_OSWORLD_SAMPLE_LIMIT", "20")).strip()
    if not raw or raw.lower() in {"none", "all", "-1"}:
        return None
    try:
        return max(1, int(raw))
    except Exception:
        return 20


@declare_task()
def task() -> Task:
    adapter = OSWorldBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return adapter.load_tasks(split="test", limit=_sample_limit())[0]
