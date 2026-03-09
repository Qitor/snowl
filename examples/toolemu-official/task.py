from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.toolemu import ToolEmuBenchmarkAdapter
from snowl.benchmarks.example_task import env_task_limit, env_task_split, load_single_task
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "ToolEmu" / "assets" / "all_cases.json"


@declare_task()
def task() -> Task:
    adapter = ToolEmuBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return load_single_task(
        adapter,
        split=env_task_split("SNOWL_TOOLEMU_SPLIT", "official"),
        limit=env_task_limit("SNOWL_TOOLEMU_LIMIT"),
    )
