"""Task loader for AgentSafetyBench evaluation."""

from pathlib import Path

from snowl.benchmarks.agentsafetybench import AgentSafetyBenchBenchmarkAdapter
from snowl.benchmarks.example_task import load_single_task
from snowl.core import task as declare_task, Task
from snowl.project_config import load_project_config

PROJECT = load_project_config(Path(__file__).parent)


@declare_task()
def task() -> Task:
    adapter = AgentSafetyBenchBenchmarkAdapter()
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "official",
        limit=PROJECT.eval.limit,
    )
