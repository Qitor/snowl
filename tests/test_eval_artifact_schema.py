from __future__ import annotations

import asyncio
import json
from pathlib import Path

from snowl.aggregator import AGGREGATE_SCHEMA_URI, RESULT_SCHEMA_URI, RESULT_SCHEMA_VERSION
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

    aggregate = json.loads((out_dir / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["schema_uri"] == AGGREGATE_SCHEMA_URI
    assert aggregate["schema_version"] == RESULT_SCHEMA_VERSION

    outcomes = json.loads((out_dir / "outcomes.json").read_text(encoding="utf-8"))
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
    assert manifest["research_exports"]["trials_jsonl"] == "trials.jsonl"
