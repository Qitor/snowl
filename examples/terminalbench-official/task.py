from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.terminalbench import TerminalBenchBenchmarkAdapter
from snowl.core import Task, task as declare_task


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "terminal-bench" / "original-tasks"

@declare_task()
def task() -> Task:
    adapter = TerminalBenchBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    return load_single_task(adapter, split="test", limit=1)
