from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.core import Task, task as declare_task
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "terminal-bench" / "original-tasks"
PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = TerminalBenchBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    base_task = load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit if PROJECT.eval.limit is not None else 1,
    )
    compose_build = bool(PROJECT.benchmark_settings("terminalbench").get("compose_build", True))
    return Task(
        task_id=base_task.task_id,
        env_spec=base_task.env_spec,
        sample_iter_factory=base_task.sample_iter_factory,
        metadata={
            **dict(base_task.metadata),
            "compose_build": compose_build,
            "runtime_container": {
                "benchmark": "terminalbench",
                "provider_name": "terminalbench",
                "requires_container": False,
                "cleanup_policy": "destroy_on_release",
                "startup": {
                    "compose_build": compose_build,
                },
                "spec_hash_basis": {
                    "compose_build": compose_build,
                },
            },
        },
    )
