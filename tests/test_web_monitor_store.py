from __future__ import annotations

import json
from pathlib import Path

from snowl.web.monitor import RunMonitorStore


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_monitor_store_discovers_runs_and_aggregates_experiment(tmp_path: Path) -> None:
    runs_root = tmp_path / ".snowl" / "runs"
    run_dir = runs_root / "20260309T120000Z"
    by_run_id = runs_root / "by_run_id"
    run_dir.mkdir(parents=True)
    by_run_id.mkdir(parents=True)

    run_id = "run-20260309T120000Z"
    (by_run_id / run_id).write_text(str(run_dir), encoding="utf-8")

    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "experiment_id": "exp-1",
            "event_stream_mode": "live_append",
        },
    )
    _write_json(run_dir / "plan.json", {"trial_count": 2})
    _write_json(run_dir / "summary.json", {"total": 2, "success": 1, "incorrect": 0, "error": 1, "limit_exceeded": 0, "cancelled": 0})
    _write_json(
        run_dir / "aggregate.json",
        {
            "by_task_agent": {
                "t1::a1": {
                    "task_id": "t1",
                    "agent_id": "a1",
                    "metrics": {"accuracy": 0.8, "safety": 0.7},
                }
            }
        },
    )

    events = [
        {
            "schema_version": "v1",
            "run_id": run_id,
            "event_index": 1,
            "event_id": f"{run_id}:1",
            "event": "pretask.start",
            "trial_key": "t1::a1::default::s1",
            "status": "running",
            "benchmark": "terminalbench",
            "agent_id": "a1",
            "variant_id": "default",
            "task_id": "t1",
            "sample_id": "s1",
            "ts_ms": 1,
            "experiment_id": "exp-1",
        },
        {
            "schema_version": "v1",
            "run_id": run_id,
            "event_index": 2,
            "event_id": f"{run_id}:2",
            "event": "runtime.trial.finish",
            "trial_key": "t1::a1::default::s1",
            "benchmark": "terminalbench",
            "agent_id": "a1",
            "variant_id": "default",
            "task_id": "t1",
            "sample_id": "s1",
            "ts_ms": 2,
            "experiment_id": "exp-1",
        },
    ]
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in events) + "\n", encoding="utf-8")

    store = RunMonitorStore(project_dir=tmp_path)
    try:
        stats = store.poll_once()
        assert stats["runs"] == 1
        exps = store.list_experiments()
        assert exps and exps[0]["experiment_id"] == "exp-1"

        runs = store.list_runs(experiment_id="exp-1")
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"

        summary = store.experiment_summary(experiment_id="exp-1", primary_dimension="agent")
        assert summary["run_count"] == 1
        assert summary["agents"]
        assert summary["agents"][0]["agent_id"] == "a1"

        pretask = store.get_pretask_events(run_id=run_id, trial_key="t1::a1::default::s1")
        assert pretask and pretask[0]["event"] == "pretask.start"

        backfill = store.backfill_events(run_id=run_id, last_event_id=f"{run_id}:1", limit=10)
        assert len(backfill) == 1
        assert backfill[0]["event"] == "runtime.trial.finish"
    finally:
        store.close()
