from __future__ import annotations

import json
from pathlib import Path

from snowl.project_config import load_project_config
from snowl.core import EnvSpec, Score, Task, TaskResult, TaskStatus
from snowl.eval_spec import EvalSpec
from snowl.observability.events import RunEventBus
from snowl.planning import PlanBuilder, trial_key, trial_models
from snowl.runtime import TrialOutcome
from snowl.runtime.policy import RuntimePolicy
from snowl.runtime.recovery import RecoveryManager
from snowl.runtime.results import to_serializable_outcome


class _Agent:
    def __init__(self, *, agent_id: str, variant_id: str = "default", model: str | None = None) -> None:
        self.agent_id = agent_id
        self.variant_id = variant_id
        self.model = model


def _task(
    task_id: str,
    *,
    env_type: str = "local",
    samples: list[dict[str, object]] | None = None,
    metadata: dict[str, object] | None = None,
) -> Task:
    return Task(
        task_id=task_id,
        env_spec=EnvSpec(env_type=env_type),
        sample_iter_factory=lambda: iter(samples or [{"id": "s1", "input": "x"}]),
        metadata=metadata or {},
    )


def _outcome(*, status: TaskStatus, variant_id: str = "default") -> TrialOutcome:
    return TrialOutcome(
        task_result=TaskResult(
            task_id="t1",
            agent_id="a1",
            sample_id="s1",
            seed=None,
            status=status,
            final_output={},
            payload={"variant_id": variant_id, "model": "m1"},
        ),
        scores={"accuracy": Score(value=1.0 if status == TaskStatus.SUCCESS else 0.0)},
        trace={"trace_events": []},
    )


def test_eval_spec_normalizes_legacy_directory_inputs(tmp_path: Path) -> None:
    spec = EvalSpec.from_legacy(
        entry_path=tmp_path,
        base_dir=tmp_path,
        source_metadata={"kind": "eval"},
    )

    assert spec.entry_path == tmp_path
    assert spec.base_dir == tmp_path
    assert spec.benchmark == "custom"
    assert spec.project_config is None
    assert spec.source_metadata == {"kind": "eval"}


def test_eval_spec_normalizes_project_config_inputs(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text("", encoding="utf-8")
    (tmp_path / "agent.py").write_text("", encoding="utf-8")
    (tmp_path / "scorer.py").write_text("", encoding="utf-8")
    (tmp_path / "project.yml").write_text(
        """
project:
  name: spec-demo
  root_dir: .
provider:
  id: demo
  kind: openai_compatible
  base_url: https://example.com/v1
  api_key: sk-test
agent_matrix:
  models:
    - id: tested
      model: demo-model
eval:
  benchmark: custombench
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
""",
        encoding="utf-8",
    )

    project = load_project_config(tmp_path)
    spec = EvalSpec.from_project(
        entry_path=tmp_path / "project.yml",
        project_config=project,
        source_metadata={"kind": "eval"},
    )

    assert spec.entry_path == tmp_path / "project.yml"
    assert spec.base_dir == tmp_path
    assert spec.benchmark == "custombench"
    assert spec.source_kind == "eval"
    assert spec.code_config == project.eval.code
    assert spec.project_config is project
    assert spec.source_metadata == {"kind": "eval"}


def test_plan_builder_preserves_matrix_shape_and_trial_identity() -> None:
    plan = PlanBuilder().build(
        [
            _task("t1", samples=[{"id": "s1", "input": "x"}, {"input": "no explicit id"}]),
            _task("t2", samples=[{"id": "s2", "input": "y"}]),
        ],
        [_Agent(agent_id="a1", variant_id="v1", model="m1"), _Agent(agent_id="a1", variant_id="v2")],
    )

    assert plan.mode == "matrix"
    assert plan.task_ids == ["t1", "t2"]
    assert plan.agent_ids == ["a1"]
    assert plan.variant_ids == ["v1", "v2"]
    assert plan.sample_count == 3
    assert len(plan.trials) == 6
    assert trial_key(plan.trials[0]) == "t1::a1::v1::s1"
    assert trial_key(plan.trials[2]).startswith("t1::a1::v1::")
    assert trial_models(plan)["t1::a1::v1::s1"] == "m1"


def test_runtime_policy_keeps_docker_like_default_serial_but_honors_explicit_parallelism() -> None:
    policy = RuntimePolicy()
    terminal_task = _task("t1", env_type="terminal", metadata={"benchmark": "terminalbench"})

    implicit = policy.resolve(
        tasks=[terminal_task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=None,
        max_container_slots=2,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets=None,
    )
    assert implicit.max_running_trials == 1
    assert implicit.max_container_slots == 2
    assert implicit.provider_budgets == {"default": implicit.max_scoring_tasks}
    assert implicit.docker_like is True

    explicit = policy.resolve(
        tasks=[terminal_task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=3,
        max_container_slots=2,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets={"p1": 7},
    )
    assert explicit.max_running_trials == 3
    assert explicit.provider_budgets == {"p1": 7}


def test_event_bus_enriches_live_events_and_derives_pretask_events(tmp_path: Path) -> None:
    plan = PlanBuilder().build([_task("t1", metadata={"benchmark": "terminalbench"})], [_Agent(agent_id="a1")])
    trial = plan.trials[0]
    bus = RunEventBus(
        events_path=tmp_path / "events.jsonl",
        runtime_state_path=tmp_path / "runtime_state.json",
        run_id="run-1",
        experiment_id="exp-1",
        benchmark="terminalbench",
        started_ts_ms=1000,
        schema_version="2025-10-01",
    )

    rows = bus.append(
        {
            "event": "runtime.env.command.finish",
            "command_text": "docker compose -p p1 -f compose.yml up -d",
            "exit_code": 0,
            "ts_ms": 1200,
        },
        trial=trial,
    )
    bus.mark_completed(ts_ms=1300)
    bus.close()

    assert [row["event"] for row in rows] == ["runtime.env.command.finish", "pretask.start"]
    assert [row["event_index"] for row in rows] == [1, 2]
    assert {row["trial_key"] for row in rows} == {"t1::a1::default::s1"}
    assert all(row["experiment_id"] == "exp-1" for row in rows)

    disk_rows = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert disk_rows == rows
    runtime_state = json.loads((tmp_path / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_state["status"] == "completed"
    assert runtime_state["heartbeat_ts_ms"] == 1300


def test_recovery_manager_bootstraps_and_supersedes_effective_attempt(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "run-1"
    initial = _outcome(status=TaskStatus.ERROR)
    (run_dir / "outcomes.json").write_text(
        json.dumps(
            [
                to_serializable_outcome(
                    initial,
                    schema_version="2025-10-01",
                    schema_uri="https://example.test/schema",
                )
            ]
        ),
        encoding="utf-8",
    )

    manager = RecoveryManager(
        run_dir=run_dir,
        run_id=run_id,
        schema_version="2025-10-01",
        schema_uri="https://example.test/schema",
    )
    key = "t1::a1::default::s1"
    effective = manager.effective_rows()
    assert effective[key]["status"] == "error"
    assert effective[key]["retry_source"] == "initial_run"

    plan = PlanBuilder().build([_task("t1")], [_Agent(agent_id="a1", model="m1")])
    manager.record_attempt(
        effective_rows=effective,
        key=key,
        trial=plan.trials[0],
        outcome=_outcome(status=TaskStatus.SUCCESS),
        retry_source="auto_retry",
        current_effective_outcomes={},
    )
    manager.write()

    recovery = json.loads((run_dir / "recovery.json").read_text(encoding="utf-8"))
    attempts = recovery["attempts_by_trial"][key]
    assert [row["retry_source"] for row in attempts] == ["initial_run", "auto_retry"]
    assert attempts[0]["effective"] is False
    assert attempts[0]["superseded_by_attempt_id"] == attempts[1]["attempt_id"]
    assert attempts[1]["status"] == "success"
    assert recovery["effective_attempts"][key] == attempts[1]["attempt_id"]
    assert len((run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()) == 2
