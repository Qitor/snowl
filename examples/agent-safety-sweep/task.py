"""Minimal task module for agent-safety-sweep.

In suite/bench mode, the benchmark adapter provides tasks.
This file exists to satisfy the project.yml `task_module` requirement.
"""

from snowl.core import task as declare_task


@declare_task(task_id="placeholder")
def tasks():
    return []
