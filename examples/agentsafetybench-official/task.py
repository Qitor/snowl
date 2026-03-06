from __future__ import annotations

import os
from pathlib import Path

from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "Agent-SafetyBench" / "data" / "released_data.json"


@declare_task()
def task() -> Task:
    adapter = AgentSafetyBenchBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    split = str(os.getenv("SNOWL_AGENTSAFETYBENCH_SPLIT", "official")).strip() or "official"
    raw_limit = str(os.getenv("SNOWL_AGENTSAFETYBENCH_LIMIT", "")).strip()
    limit = int(raw_limit) if raw_limit else None
    return adapter.load_tasks(split=split, limit=limit)[0]
