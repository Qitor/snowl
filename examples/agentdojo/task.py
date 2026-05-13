"""Task definition for AgentDojo eval."""

from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.agentdojo import AgentDojoBenchmarkAdapter
from snowl.benchmarks.example_task import load_single_task
from snowl.core import Task, task as declare_task
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
PROJECT = load_project_config(Path(__file__).parent)


@declare_task()
def task() -> Task:
    adapter = AgentDojoBenchmarkAdapter()
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "official",
        limit=PROJECT.eval.limit,
    )
