from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from snowl.aggregator import AGGREGATE_SCHEMA_URI, RESULT_SCHEMA_URI, RESULT_SCHEMA_VERSION
from snowl.bench import run_benchmark
from snowl.core import (
    AgentContext,
    AgentState,
    EnvSpec,
    ErrorInfo,
    SandboxSpec,
    Score,
    ScoreContext,
    Task,
    TaskResult,
    TaskStatus,
    Timing,
    Usage,
    validate_agent,
    validate_scorer,
    validate_task,
    validate_task_result,
    validate_scores,
)
from snowl.core import tool
from snowl.envs.sandbox_runtime import PreparedSandbox
from snowl.errors import SnowlValidationError
from snowl.eval import run_eval
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.runtime import TrialRequest, execute_trial


class _PassScorer:
    scorer_id = "pass"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0)}


def _write_local_project(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text(
        """
from snowl.core import EnvSpec, Task

task = Task(
    task_id="t1",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([{"id":"s1", "input":"hello"}]),
)
""",
        encoding="utf-8",
    )
    (tmp_path / "agent.py").write_text(
        """
from snowl.core import StopReason

class A:
    agent_id = "a1"
    async def run(self, state, context, tools=None):
        _ = (context, tools)
        state.output = {
            "message": {"role":"assistant", "content":"ok"},
            "usage": {"input_tokens":1, "output_tokens":1, "total_tokens":2},
            "trace_events": [{"event": "agent.run"}],
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
        _ = (task_result, trace, context)
        return {"accuracy": Score(value=1.0), "latency": Score(value=0.9)}

scorer = S()
""",
        encoding="utf-8",
    )


def test_core_contract_unit_validation_matrix() -> None:
    task = Task(task_id="task-1", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: iter([{"id": "s1"}]))
    validate_task(task)

    class AgentOK:
        agent_id = "agent-ok"

        async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
            _ = (context, tools)
            return state

    validate_agent(AgentOK())

    class ScorerOK:
        scorer_id = "scorer-ok"

        def score(self, task_result: TaskResult, trace, context: ScoreContext):
            _ = (task_result, trace, context)
            return {"accuracy": Score(value=1.0)}

    validate_scorer(ScorerOK())
    validate_scores({"accuracy": Score(value=1.0)})

    result = TaskResult(
        task_id="task-1",
        agent_id="agent-ok",
        sample_id="s1",
        seed=7,
        status=TaskStatus.ERROR,
        timing=Timing(started_at_ms=1, ended_at_ms=2, duration_ms=1),
        usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
        error=ErrorInfo(code="x", message="boom"),
    )
    validate_task_result(result)

    with pytest.raises(SnowlValidationError, match="sample_iter_factory"):
        validate_task(Task(task_id="bad-task", env_spec=EnvSpec(env_type="local"), sample_iter_factory=lambda: 1))  # type: ignore[arg-type]
    with pytest.raises(SnowlValidationError, match="run"):
        validate_agent(type("BadAgent", (), {"agent_id": "x"})())
    with pytest.raises(SnowlValidationError, match="Score instance"):
        validate_scores({"accuracy": 1.0})  # type: ignore[arg-type]


def test_local_three_file_flow_regression_snapshot(tmp_path: Path) -> None:
    _write_local_project(tmp_path)
    result = asyncio.run(run_eval(tmp_path, renderer=None))
    out_dir = Path(result.artifacts_dir)

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    aggregate = json.loads((out_dir / "aggregate.json").read_text(encoding="utf-8"))
    outcomes = json.loads((out_dir / "outcomes.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    snapshot = {
        "summary": summary,
        "aggregate_matrix": aggregate["matrix"],
        "outcome_statuses": [row["task_result"]["status"] for row in outcomes],
        "outcome_ids": [
            (
                row["task_result"]["task_id"],
                row["task_result"]["agent_id"],
                row["task_result"]["sample_id"],
            )
            for row in outcomes
        ],
        "manifest_static": {
            "schema_version": manifest["schema_version"],
            "result_schema_uri": manifest["result_schema_uri"],
            "aggregate_schema_uri": manifest["aggregate_schema_uri"],
            "diagnostics_count": manifest["diagnostics_count"],
        },
    }

    assert snapshot == {
        "summary": {
            "total": 1,
            "success": 1,
            "incorrect": 0,
            "error": 0,
            "limit_exceeded": 0,
            "cancelled": 0,
        },
        "aggregate_matrix": {"t1": {"a1": {"accuracy": 1.0, "latency": 0.9}}},
        "outcome_statuses": ["success"],
        "outcome_ids": [("t1", "a1", "s1")],
        "manifest_static": {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_schema_uri": RESULT_SCHEMA_URI,
            "aggregate_schema_uri": AGGREGATE_SCHEMA_URI,
            "diagnostics_count": 0,
        },
    }
    assert manifest["rerun_command"].startswith("snowl eval ")


def test_benchmark_taskprovider_integration_deterministic_ids_and_manifest(tmp_path: Path) -> None:
    _write_local_project(tmp_path)
    dataset = tmp_path / "bench.jsonl"
    rows = [
        {"id": "case-1", "split": "test", "input": "x", "target": "y"},
        {"id": "case-2", "split": "test", "input": "x2", "target": "y2"},
    ]
    with dataset.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    result = asyncio.run(
        run_benchmark(
            "jsonl",
            project_path=tmp_path,
            split="test",
            limit=None,
            benchmark_args=[f"dataset_path={dataset}"],
            renderer=None,
        )
    )
    out_dir = Path(result.artifacts_dir)
    outcomes = json.loads((out_dir / "outcomes.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    sample_ids = sorted(str(row["task_result"]["sample_id"]) for row in outcomes)
    task_ids = {row["task_result"]["task_id"] for row in outcomes}
    assert sample_ids == ["case-1", "case-2"]
    assert task_ids == {"jsonl:test"}
    assert "snowl bench run jsonl" in manifest["rerun_command"]
    assert "--split test" in manifest["rerun_command"]


def test_failure_paths_tool_error_and_sandbox_failure() -> None:
    @tool
    def boom(value: str) -> str:
        """Always fail."""

        raise RuntimeError(f"tool failed for {value}")

    class ToolAgent:
        agent_id = "tool-agent"

        async def run(self, state, context, tools=None):
            _ = context
            tool_spec = list(tools or [])[0]
            tool_spec.callable(value="x")
            return state

    class FailingSandboxRuntime:
        async def prepare(self, spec):
            _ = spec
            return PreparedSandbox(
                sandbox_id="sb-1",
                spec_hash="abc",
                provider="docker",
                prepared_at_ms=1,
                diagnostics={"phase": "prepare"},
            )

        async def run(self, prepared, operation):
            _ = (prepared, operation)
            raise RuntimeError("sandbox runtime crashed")

        async def teardown(self, prepared):
            _ = prepared
            return {"phase": "teardown", "reason": "runtime_crash"}

    task = Task(
        task_id="tool-failure",
        env_spec=EnvSpec(
            env_type="docker",
            provided_ops=("FileOps",),
            sandbox_spec=SandboxSpec(provider="docker", image="python:3.12"),
        ),
        sample_iter_factory=lambda: iter([]),
    )

    req = TrialRequest(
        task=task,
        agent=ToolAgent(),
        scorer=_PassScorer(),
        sample={"id": "s1", "input": "hello"},
        tools=[boom],
        sandbox_runtime=FailingSandboxRuntime(),
    )
    out = asyncio.run(execute_trial(req))
    assert out.task_result.status.value == "error"
    assert out.task_result.error is not None
    assert out.task_result.error.code == "agent_runtime_error"
    assert "sandbox runtime crashed" in out.task_result.error.message
    assert out.trace["stop_reason"] == "error"
    assert out.trace["sandbox"]["teardown"]["reason"] == "runtime_crash"


def test_model_retry_path_recovers_after_transient_error() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="gpt-test",
            timeout=5,
            max_retries=1,
        ),
        transport=httpx.MockTransport(handler),
        retry_backoff_seconds=0,
    )

    async def _run() -> None:
        response = await client.generate([{"role": "user", "content": "hello"}])
        assert response.message["content"] == "ok"
        assert calls["n"] == 2
        await client.aclose()

    asyncio.run(_run())
