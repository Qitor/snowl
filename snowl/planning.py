"""Internal eval planning primitives.

This module is the first extraction from ``snowl.eval``'s control plane. It
keeps the public eval behavior unchanged while giving future runtime work a
stable place for plan and trial identity logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from snowl.core import Agent, Scorer, Task


@dataclass(frozen=True)
class PlanTrial:
    task: Task
    agent: Agent
    sample: dict[str, Any]
    task_id: str
    agent_id: str
    variant_id: str
    model: str | None
    sample_id: str | None
    scorer_id: str = "default"


@dataclass(frozen=True)
class EvalPlan:
    mode: str
    task_ids: list[str]
    agent_ids: list[str]
    variant_ids: list[str]
    sample_count: int
    trials: list[PlanTrial]
    scorer_ids: list[str] = field(default_factory=list)


class PlanBuilder:
    """Build deterministic internal plans from already-discovered components.

    The builder owns only Task x Agent x Sample (x Scorer) expansion and trial identity.
    It does not load projects, apply CLI filters, schedule work, or persist
    artifacts.
    """

    def build(self, tasks: list[Task], agents: list[Agent], scorers: list[Scorer] | None = None) -> EvalPlan:
        return build_plan(tasks, agents, scorers)


def build_plan(tasks: list[Task], agents: list[Agent], scorers: list[Scorer] | None = None) -> EvalPlan:
    task_ids = [t.task_id for t in tasks]
    agent_ids = sorted({getattr(a, "agent_id") for a in agents})
    variant_ids = sorted({str(getattr(a, "variant_id", "default")) for a in agents})

    # When multiple scorers are provided, expand the plan to include scorer dimension
    scorer_specs: list[tuple[str | None, str]] = []
    if scorers and len(scorers) > 1:
        for s in scorers:
            s_id = getattr(s, "scorer_id", None)
            scorer_specs.append((s_id, str(s_id) if s_id is not None else "default"))
    else:
        # Single or no scorer: use default scorer_id
        scorer_specs.append((None, "default"))

    sample_buckets: list[tuple[Task, list[dict[str, Any]]]] = []
    sample_count = 0
    for task in tasks:
        samples = [dict(sample) for sample in task.iter_samples()]
        sample_count += len(samples)
        sample_buckets.append((task, samples))

    trials: list[PlanTrial] = []
    for task, samples in sample_buckets:
        for sample in samples:
            sample_id = str(sample.get("id")) if sample.get("id") is not None else None
            for agent in agents:
                for _scorer_obj, scorer_id in scorer_specs:
                    trials.append(
                        PlanTrial(
                            task=task,
                            agent=agent,
                            sample=sample,
                            task_id=task.task_id,
                            agent_id=getattr(agent, "agent_id"),
                            variant_id=str(getattr(agent, "variant_id", "default")),
                            model=(
                                str(getattr(agent, "model"))
                                if getattr(agent, "model", None) is not None
                                else None
                            ),
                            sample_id=sample_id,
                            scorer_id=scorer_id,
                        )
                    )

    if len(task_ids) == 1 and len(agent_ids) == 1 and len(variant_ids) == 1:
        mode = "single"
    elif len(task_ids) > 1 and len(agent_ids) == 1 and len(variant_ids) == 1:
        mode = "task_sweep"
    elif len(task_ids) == 1 and (len(agent_ids) > 1 or len(variant_ids) > 1):
        mode = "agent_compare"
    else:
        mode = "matrix"

    scorer_ids_list = sorted({sid for _, sid in scorer_specs})

    return EvalPlan(
        mode=mode,
        task_ids=task_ids,
        agent_ids=agent_ids,
        variant_ids=variant_ids,
        sample_count=sample_count,
        trials=trials,
        scorer_ids=scorer_ids_list,
    )


def trial_key(trial: PlanTrial) -> str:
    if trial.sample_id is not None:
        sample_token = trial.sample_id
    else:
        sample_json = json.dumps(trial.sample, ensure_ascii=False, sort_keys=True)
        sample_token = hashlib.sha1(sample_json.encode("utf-8")).hexdigest()[:12]
    scorer_suffix = f"::{trial.scorer_id}" if trial.scorer_id != "default" else ""
    return f"{trial.task_id}::{trial.agent_id}::{trial.variant_id}::{sample_token}{scorer_suffix}"


def trial_models(plan: EvalPlan) -> dict[str, str | None]:
    return {trial_key(trial): trial.model for trial in plan.trials}
