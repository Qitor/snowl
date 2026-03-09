from __future__ import annotations

import asyncio

import httpx

from snowl.agents import ChatAgent
from snowl.core import EnvSpec, Score, ScoreContext, Task, TaskResult
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.runtime import TrialLimits, TrialRequest, execute_trial


class PassScorer:
    scorer_id = "pass"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=1.0)}


class FailScorer:
    scorer_id = "fail"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"accuracy": Score(value=0.0)}


class MetricOnlyScorer:
    scorer_id = "metric"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        return {"latency": Score(value=0.5)}


class ExplodingScorer:
    scorer_id = "explode"

    def score(self, task_result: TaskResult, trace, context: ScoreContext):
        raise RuntimeError("boom")


def _task() -> Task:
    return Task(
        task_id="task-1",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([]),
    )


def test_execute_trial_success_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
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

    req = TrialRequest(
        task=_task(),
        agent=ChatAgent(model_client=client),
        scorer=PassScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "success"
        assert out.scores["accuracy"].value == 1.0
        await client.aclose()

    asyncio.run(_run())


def test_execute_trial_incorrect_status_when_accuracy_below_one() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "wrong"}}],
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

    req = TrialRequest(
        task=_task(),
        agent=ChatAgent(model_client=client),
        scorer=FailScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "incorrect"
        await client.aclose()

    asyncio.run(_run())


def test_execute_trial_token_limit_exceeded() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
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

    req = TrialRequest(
        task=_task(),
        agent=ChatAgent(model_client=client),
        scorer=MetricOnlyScorer(),
        sample={"id": "s1", "input": "hello"},
        limits=TrialLimits(token_limit=4),
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "limit_exceeded"
        assert out.task_result.error is not None
        assert out.task_result.error.code == "token_limit_exceeded"
        await client.aclose()

    asyncio.run(_run())


def test_execute_trial_time_limit_exceeded() -> None:
    class SlowAgent:
        agent_id = "slow"

        async def run(self, state, context, tools=None):
            await asyncio.sleep(0.05)
            return state

    req = TrialRequest(
        task=_task(),
        agent=SlowAgent(),
        scorer=MetricOnlyScorer(),
        sample={"id": "s1", "input": "hello"},
        limits=TrialLimits(time_limit_seconds=0.001),
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "limit_exceeded"
        assert out.task_result.error is not None
        assert out.task_result.error.code == "time_limit_exceeded"

    asyncio.run(_run())


def test_execute_trial_max_steps_limit_via_agent_override() -> None:
    class StepAgent:
        agent_id = "step-agent"

        def __init__(self) -> None:
            self.max_steps = 99

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            if self.max_steps <= 1:
                state.stop_reason = StopReason.MAX_STEPS
            return state

    req = TrialRequest(
        task=_task(),
        agent=StepAgent(),
        scorer=MetricOnlyScorer(),
        sample={"id": "s1", "input": "hello"},
        limits=TrialLimits(max_steps=1),
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "limit_exceeded"
        assert out.task_result.payload.get("stop_reason") == "max_steps"

    asyncio.run(_run())


def test_execute_trial_artifacts_passthrough() -> None:
    class ArtifactAgent:
        agent_id = "artifact-agent"

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            state.output = {
                "message": {"role": "assistant", "content": "ok"},
                "artifacts": [
                    {
                        "name": "recording_mp4",
                        "uri": "C:/tmp/recording.mp4",
                        "media_type": "video/mp4",
                    }
                ],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

    req = TrialRequest(
        task=_task(),
        agent=ArtifactAgent(),
        scorer=PassScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "success"
        assert len(out.task_result.artifacts) == 1
        assert out.task_result.artifacts[0].name == "recording_mp4"
        assert out.task_result.artifacts[0].uri == "C:/tmp/recording.mp4"

    asyncio.run(_run())


def test_execute_trial_artifacts_preserved_when_incorrect() -> None:
    class ArtifactAgent:
        agent_id = "artifact-agent"

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            state.output = {
                "message": {"role": "assistant", "content": "not ok"},
                "artifacts": [{"name": "recording_mp4", "uri": "C:/tmp/recording.mp4"}],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

    req = TrialRequest(
        task=_task(),
        agent=ArtifactAgent(),
        scorer=FailScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "incorrect"
        assert len(out.task_result.artifacts) == 1
        assert out.task_result.artifacts[0].name == "recording_mp4"

    asyncio.run(_run())


def test_execute_trial_artifacts_preserved_when_scorer_errors() -> None:
    class ArtifactAgent:
        agent_id = "artifact-agent"

        async def run(self, state, context, tools=None):
            from snowl.core import StopReason

            state.output = {
                "message": {"role": "assistant", "content": "ok"},
                "artifacts": [{"name": "recording_mp4", "uri": "C:/tmp/recording.mp4"}],
            }
            state.stop_reason = StopReason.COMPLETED
            return state

    req = TrialRequest(
        task=_task(),
        agent=ArtifactAgent(),
        scorer=ExplodingScorer(),
        sample={"id": "s1", "input": "hello"},
    )

    async def _run() -> None:
        out = await execute_trial(req)
        assert out.task_result.status.value == "error"
        assert out.task_result.error is not None
        assert out.task_result.error.code == "scorer_error"
        assert len(out.task_result.artifacts) == 1
        assert out.task_result.artifacts[0].name == "recording_mp4"

    asyncio.run(_run())
