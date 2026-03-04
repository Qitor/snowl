from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "OSWorld" / "evaluation_examples"

@declare_task()
def task() -> Task:
    adapter = OSWorldBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return adapter.load_tasks(split="test", limit=20)[0]
