from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.example_task import load_single_task
from snowl.core import Task, task as declare_task
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "Agent-SafetyBench" / "data" / "released_data.json"
PROJECT = load_project_config(Path(__file__).parent)


@declare_task()
def task() -> Task:
    adapter = AgentSafetyBenchBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "official",
        limit=PROJECT.eval.limit,
    )
