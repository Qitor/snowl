from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.example_task import env_task_sample_limit, load_single_task
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "OSWorld" / "evaluation_examples"

@declare_task()
def task() -> Task:
    adapter = OSWorldBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return load_single_task(
        adapter,
        split="test",
        limit=env_task_sample_limit("SNOWL_OSWORLD_SAMPLE_LIMIT", default=20),
    )
