from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.aggregator import (
    AGGREGATE_SCHEMA_URI,
    BENCHMARK_SUMMARY_SCHEMA_URI,
    DOMAIN_SUMMARY_SCHEMA_URI,
    RESULT_SCHEMA_URI,
    RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION_V2,
)
from snowl.eval import run_eval


def test_eval_writes_schema_manifest_and_aggregate(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(task_id="t1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id":"s1", "input":"x"}]))
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        state.output = {
            "message": {"role":"assistant", "content":"ok"},
            "traj": [
                {"role": "user", "content": "prompt"},
                {"role": "assistant", "content": "ok"},
            ],
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [],
        }
        state.stop_reason = StopReason.COMPLETED
        return state

agent = A()
""",
        encoding="utf-8",
    )
    (tmp_path / "scorer.py").write_text(
        """
from snowl.core import Score
class S:
    scorer_id = "s1"
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
scorer = S()
""",
        encoding="utf-8",
    )

    result = asyncio.run(run_eval(tmp_path, renderer=None))
    out_dir = Path(result.artifacts_dir)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == RESULT_SCHEMA_VERSION
    assert manifest["result_schema_uri"] == RESULT_SCHEMA_URI
    assert manifest["aggregate_schema_uri"] == AGGREGATE_SCHEMA_URI
    assert manifest["event_stream_mode"] == "live_append"
    assert manifest["runtime_state"] == "runtime_state.json"
    assert manifest["source"]["kind"] == "eval"
    assert manifest["recovery"]["ledger"] == "recovery.json"

    aggregate = json.loads((out_dir / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["schema_uri"] == AGGREGATE_SCHEMA_URI
    assert aggregate["schema_version"] == RESULT_SCHEMA_VERSION
    assert "by_task_agent" in aggregate
    assert "matrix" in aggregate

    benchmark_summary = json.loads((out_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert benchmark_summary["schema_uri"] == BENCHMARK_SUMMARY_SCHEMA_URI
    assert benchmark_summary["schema_version"] == RESULT_SCHEMA_VERSION_V2
    assert isinstance(benchmark_summary["rows"], list)

    domain_summary = json.loads((out_dir / "domain_summary.json").read_text(encoding="utf-8"))
    assert domain_summary["schema_uri"] == DOMAIN_SUMMARY_SCHEMA_URI
    assert domain_summary["schema_version"] == RESULT_SCHEMA_VERSION_V2
    assert isinstance(domain_summary["rows"], list)

    outcomes = json.loads((out_dir / "outcomes.json").read_text(encoding="utf-8"))
    assert len(outcomes) == 1
    assert outcomes[0]["schema_version"] == RESULT_SCHEMA_VERSION
    assert outcomes[0]["schema_uri"] == RESULT_SCHEMA_URI
    assert outcomes[0]["task_result"]["final_output"]["traj"] == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": "ok"},
    ]
    assert (out_dir / "run.log").exists()
    log_text = (out_dir / "run.log").read_text(encoding="utf-8")
    assert "trial_start" in log_text
    by_run_id = out_dir.parent / "by_run_id"
    if by_run_id.exists():
        pointers = list(by_run_id.iterdir())
        matched = False
        for pointer in pointers:
            if pointer.is_symlink():
                if pointer.resolve() == out_dir.resolve():
                    matched = True
                    break
            else:
                if pointer.read_text(encoding="utf-8").strip() == str(out_dir):
                    matched = True
                    break
        assert matched is True
    assert (out_dir / "trials.jsonl").exists()
    assert (out_dir / "events.jsonl").exists()
    assert (out_dir / "metrics_wide.csv").exists()
    assert (out_dir / "leaderboard_rows.jsonl").exists()
    assert manifest["research_exports"]["trials_jsonl"] == "trials.jsonl"

    trial_rows = [
        json.loads(line)
        for line in (out_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(trial_rows) == 1
    assert trial_rows[0]["run_id"] == manifest["run_id"]
    assert trial_rows[0]["trial_index"] == 1
    assert trial_rows[0]["task_result"]["payload"]["variant_id"] == "default"

    events = [
        json.loads(line)
        for line in (out_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert events
    assert [int(row["event_index"]) for row in events] == list(range(1, len(events) + 1))
    assert [int(row["seq"]) for row in events] == list(range(1, len(events) + 1))
    assert all(str(row["event_id"]).startswith(manifest["run_id"] + ":") for row in events)
    assert {row["experiment_id"] for row in events} == {manifest["experiment_id"]}
    assert any(row.get("trial_key") == "t1::a1::default::s1" for row in events)

    runtime_state = json.loads((out_dir / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_state["status"] == "completed"
    assert runtime_state["run_id"] == manifest["run_id"]
    assert runtime_state["heartbeat_ts_ms"] >= runtime_state["started_ts_ms"]
    assert runtime_state["ended_ts_ms"] >= runtime_state["started_ts_ms"]

    recovery = json.loads((out_dir / "recovery.json").read_text(encoding="utf-8"))
    attempt_key = "t1::a1::default::s1"
    assert recovery["effective_attempts"][attempt_key].endswith("attempt-0001")
    assert recovery["attempts_by_trial"][attempt_key][0]["effective"] is True
    assert recovery["attempts_by_trial"][attempt_key][0]["retry_source"] == "initial_run"
    attempts_jsonl = [
        json.loads(line)
        for line in (out_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(attempts_jsonl) == 1
    assert attempts_jsonl[0]["trial_key"] == attempt_key
