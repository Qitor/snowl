from __future__ import annotations

import asyncio

from snowl.core import EnvSpec, Score, ScoreContext, Task, TaskResult, ToolSpec
from snowl.runtime import TrialRequest, execute_trial
from snowl.runtime.container_providers import ContainerProviderRegistry, ContainerSession
from snowl.runtime.container_runtime import ContainerRuntime


class PassScorer:
    scorer_id = "pass"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=1.0)}


def _task(metadata=None) -> Task:
    return Task(
        task_id="task",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([]),
        metadata=dict(metadata or {}),
    )


def test_sample_dynamic_tool_schema_becomes_available_tool() -> None:
    class ToolRecordingAgent:
        agent_id = "agent"

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            tool_names = [tool.name for tool in tools or []]
            state.output = {
                "message": {"role": "assistant", "content": ",".join(tool_names)},
                "trace_events": [{"event": "tools", "tool_names": tool_names}],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

    sample = {
        "id": "s",
        "input": "use tool",
        "metadata": {
            "tool_names": ["foo"],
            "tool_schemas": [
                {
                    "type": "function",
                    "function": {
                        "name": "foo",
                        "description": "Foo tool.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
    }
    req = TrialRequest(task=_task(), agent=ToolRecordingAgent(), scorer=PassScorer(), sample=sample)

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "success"
        assert out.task_result.final_output["content"] == "foo"

    asyncio.run(_run())


def test_sample_dynamic_tool_schema_conflict_fails_prepare() -> None:
    class NoopAgent:
        agent_id = "agent"

        async def run(self, state, context, tools=None):
            return state

    project_tool = ToolSpec(
        name="foo",
        description="Foo",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        callable=lambda x: x,
    )
    sample = {
        "id": "s",
        "input": "use tool",
        "metadata": {
            "tool_names": ["foo"],
            "tool_schemas": [{"name": "foo", "parameters": {"type": "object", "properties": {}}}],
        },
    }
    req = TrialRequest(task=_task(), agent=NoopAgent(), scorer=PassScorer(), sample=sample, tools=[project_tool])

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "error"
        assert out.task_result.error is not None
        assert out.task_result.error.code == "sample_tool_schema_conflict"

    asyncio.run(_run())


def test_container_runtime_resolves_provider_name_before_benchmark() -> None:
    class Provider:
        name = "compose_terminal"

        def describe_requirements(self, context):
            return {
                "benchmark": context.container_spec.benchmark,
                "requires_container": True,
                "requires_build": False,
                "spec_hash": context.container_spec.spec_hash,
                "prepare_provider_ids": (),
            }

        async def prepare(self, context):
            return ContainerSession(kind="dummy", env=object(), benchmark=context.container_spec.benchmark)

        async def close(self, context, session):
            return {"closed": True}

    registry = ContainerProviderRegistry()
    registry.register("compose_terminal", Provider())
    runtime = ContainerRuntime(
        task_id="t",
        agent_id="a",
        variant_id="v",
        task_env_type="local",
        task_metadata={
            "benchmark": "unknown_benchmark",
            "runtime_container": {
                "benchmark": "unknown_benchmark",
                "provider_name": "compose_terminal",
                "requires_container": True,
            },
        },
        sample={"id": "s", "input": "x"},
        provider_registry=registry,
    )

    async def _run() -> None:
        result = await runtime.prepare_phase()
        assert result.requires_container is True
        assert result.session is not None
        assert result.session.kind == "dummy"
        await runtime.finalize_phase()

    asyncio.run(_run())
