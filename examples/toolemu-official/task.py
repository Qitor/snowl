from __future__ import annotations

import os
from pathlib import Path

from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "ToolEmu" / "assets" / "all_cases.json"


@declare_task()
def task() -> Task:
    split = str(os.getenv("SNOWL_TOOLEMU_SPLIT", "official")).strip() or "official"
    limit_raw = str(os.getenv("SNOWL_TOOLEMU_LIMIT", "")).strip()
    limit = int(limit_raw) if limit_raw else None
    adapter = ToolEmuBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return adapter.load_tasks(split=split, limit=limit)[0]
