from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.core import Task, task as declare_task
from snowl.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "references" / "strongreject" / "strongreject_dataset" / "strongreject_small_dataset.csv"
AIM_PATH = ROOT / "references" / "strongreject" / "strongreject" / "AIM.txt"
PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = StrongRejectBenchmarkAdapter(dataset_path=str(DATASET_PATH))
    base_task = load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit if PROJECT.eval.limit is not None else 50,
    )
    aim_template = AIM_PATH.read_text(encoding="utf-8")

    def _aim_wrapped_samples():
        for sample in base_task.iter_samples():
            row = dict(sample)
            prompt = str(row.get("metadata", {}).get("forbidden_prompt") or row.get("input") or "")
            row["input"] = aim_template.replace("[INSERT PROMPT HERE]", prompt)
            yield row

    return Task(
        task_id=base_task.task_id,
        env_spec=base_task.env_spec,
        sample_iter_factory=_aim_wrapped_samples,
        metadata=dict(base_task.metadata),
    )
