from __future__ import annotations

import asyncio

import httpx
import pytest

from snowl.agents import ChatAgent
from snowl.core import EnvSpec, SandboxSpec, Score, ScoreContext, Task, TaskResult, tool, validate_env_spec
from snowl.errors import SnowlValidationError
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.runtime import TrialRequest, execute_trial


class PassScorer:
    scorer_id = "pass"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=1.0)}


def test_validate_env_spec_rejects_empty_op_name() -> None:
    with pytest.raises(SnowlValidationError, match="provided_ops"):
        validate_env_spec(EnvSpec(env_type="local", provided_ops=("FileOps", "")))


def test_sandbox_spec_hash_is_deterministic_for_normalized_equivalent_specs() -> None:
    spec1 = SandboxSpec(
        provider="docker",
        build_context="./work/../work/project",
        image="python:3.12",
        environment={"B": "2", "A": "1"},
        command=["python", "main.py"],
    )
    spec2 = SandboxSpec(
        provider="docker",
        build_context="work/project",
        image="python:3.12",
        environment={"A": "1", "B": "2"},
        command=["python", "main.py"],
    )

    assert spec1.normalized() == spec2.normalized()
    assert spec1.spec_hash() == spec2.spec_hash()


def test_execute_trial_rejects_tool_env_ops_mismatch() -> None:
    @tool(required_ops=["FileOps"])
    def read_file(path: str) -> str:
        """Read file by path."""

        return path

    class NoopAgent:
        agent_id = "noop"

        async def run(self, state, context, tools=None):
            return state

    task = Task(
        task_id="task-ops-mismatch",
        env_spec=EnvSpec(env_type="local", provided_ops=("ProcessOps",)),
        sample_iter_factory=lambda: iter([]),
    )

    req = TrialRequest(
        task=task,
        agent=NoopAgent(),
        scorer=PassScorer(),
        sample={"id": "s1", "input": "hello"},
        tools=[read_file],
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "error"
        assert out.task_result.error is not None
        assert out.task_result.error.code == "env_ops_mismatch"
        assert out.scores == {}
        assert out.trace["trace_events"][0]["event"] == "runtime.validation_error"

    asyncio.run(_run())


def test_execute_trial_includes_sandbox_prepare_and_teardown_metadata() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
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
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )

    task = Task(
        task_id="task-sandbox",
        env_spec=EnvSpec(
            env_type="docker",
            provided_ops=(),
            sandbox_spec=SandboxSpec(provider="docker", image="python:3.12"),
        ),
        sample_iter_factory=lambda: iter([]),
    )

    req = TrialRequest(
        task=task,
        agent=ChatAgent(model_client=client),
        scorer=PassScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "success"
        sandbox_meta = out.task_result.payload.get("sandbox")
        assert sandbox_meta is not None
        assert "spec_hash" in sandbox_meta
        assert sandbox_meta["provider"] == "docker"
        assert out.trace["sandbox"]["provider"] == "docker"
        await client.aclose()

    asyncio.run(_run())
