from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.osworld import OSWorldBenchmarkAdapter
from snowl.core import Task, task as declare_task
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "OSWorld" / "evaluation_examples"
PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = OSWorldBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    base_task = load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit if PROJECT.eval.limit is not None else 20,
    )
    return Task(
        task_id=base_task.task_id,
        env_spec=base_task.env_spec,
        sample_iter_factory=base_task.sample_iter_factory,
        metadata={
            **dict(base_task.metadata),
            "osworld_settings": PROJECT.benchmark_settings("osworld"),
        },
    )
