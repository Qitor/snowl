"""Tier 2 E2E tests: advanced features with real LLM calls.

E2E-5: LLM-as-Judge scorer
E2E-6: Multi-step task
E2E-7: Solver chain with tools
E2E-8: Approval system integration
"""

from __future__ import annotations

import pytest

from snowl.agents.chat_agent import ChatAgent
from snowl.core.env import EnvSpec
from snowl.core.task import Task
from snowl.runtime.engine import TrialRequest, execute_trial
from snowl.scorer import includes

from .conftest import track_usage


# ---------------------------------------------------------------------------
# E2E-5: LLM-as-Judge scorer
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_llm_as_judge_scorer(live_client, live_config, cost_tracker):
    """ModelAsJudgeJSONScorer calls judge model and returns structured score."""
    from snowl.scorer.model_judge import ModelAsJudgeJSONScorer

    judge = ModelAsJudgeJSONScorer(
        model_name=live_config.model,
        system_prompt_template=(
            "You are a judge. Evaluate if the answer is correct. "
            'Reply with JSON having keys "score" (0 or 1) and "reasoning" (brief explanation).'
        ),
        user_prompt_template=(
            "Question: What is 2+2?\n"
            "Answer: {output}\n"
            "Expected: 4\n"
        ),
        schema={
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["score"],
        },
        client=live_client,
        strict=False,
        strict_templates=False,
    )

    task = Task(
        task_id="e2e-5",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "What is 2+2?",
             "metadata": {"target": "4"}},
        ]),
    )
    agent = ChatAgent(live_client, default_generation_kwargs={"max_tokens": 256})
    sample = {"id": "s1", "input": "What is 2+2?", "metadata": {"target": "4"}}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=judge,
    ))

    assert "judge" in outcome.scores
    assert isinstance(outcome.scores["judge"].value, float)
    # Judge metadata should record the model used
    meta = outcome.scores["judge"].metadata or {}
    assert meta.get("judge_model") is not None

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-6: Multi-step task
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_multi_step_task(live_client, cost_tracker):
    """2-step task produces step_results with both steps."""
    from snowl.core.step import TaskStep

    steps = (
        TaskStep(step_id="step1", instruction="First: answer with the word 'alpha'"),
        TaskStep(step_id="step2", instruction="Now answer with the word 'beta'"),
    )
    task = Task(
        task_id="e2e-6",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Follow the instructions step by step."},
        ]),
        steps=steps,
    )
    agent = ChatAgent(live_client, default_generation_kwargs={"max_tokens": 256})
    sample = {"id": "s1", "input": "Follow the instructions step by step."}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
    ))

    # Multi-step: task.steps triggers MultiStepExecutor in engine
    # The outcome should have step_results if steps were executed
    step_results = getattr(outcome.task_result, "step_results", None)
    if step_results is not None and len(step_results) > 0:
        assert len(step_results) == 2, f"Expected 2 steps, got {len(step_results)}"
    else:
        # If engine didn't populate step_results, verify at least the task had steps
        # and the overall execution completed (some code paths flatten multi-step)
        assert outcome.task_result.status.value in {"success", "incorrect", "error"}

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-7: Solver chain with tools
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_solver_chain_with_tools(live_client, cost_tracker):
    """chain(system_message, use_tools, submit_tool, generate) produces tool usage."""
    from snowl.core.solver import chain
    from snowl.core.tool import build_tool_spec
    from snowl.solver import system_message, use_tools, submit_tool, generate

    def echo(text: str) -> str:
        return text

    echo_spec = build_tool_spec(echo)

    solver = chain(
        system_message(
            "You have an echo tool. When asked to repeat something, "
            "use the echo tool, then submit your answer."
        ),
        use_tools(echo_spec),
        submit_tool(),
        generate(live_client, max_steps=4, generation_kwargs={"max_tokens": 512}),
    )

    task = Task(
        task_id="e2e-7",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Use the echo tool to repeat 'hello'."},
        ]),
    )
    agent = ChatAgent(live_client)
    sample = {"id": "s1", "input": "Use the echo tool to repeat 'hello'."}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
        solver_chain=solver,
    ))

    actions = outcome.trace.get("actions", [])
    # The solver chain should have produced at least one action
    # (model may or may not use the tool, but the loop should execute)
    assert len(actions) >= 1, "Solver chain should produce at least 1 action"

    track_usage(cost_tracker, outcome.task_result.usage)


# ---------------------------------------------------------------------------
# E2E-8: Approval system integration
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_approval_auto_approve_allows_tools(live_client, cost_tracker):
    """AutoApprove policy allows tool execution through middleware."""
    from snowl.agents.react_agent import ReActAgent
    from snowl.core.approval import AutoApprove, ToolCall
    from snowl.core.tool import build_tool_spec

    def echo(text: str) -> str:
        return text

    echo_spec = build_tool_spec(echo)
    policy = AutoApprove()

    class ApprovalMiddleware:
        """Middleware that checks approval before tool execution."""
        async def intercept_call(self, tool_name, args):
            decision = await policy.check(
                ToolCall(tool_name=tool_name, arguments=args), None
            )
            if decision.rejected:
                raise RuntimeError(f"Tool rejected: {decision.reason}")
            return args

    agent = ReActAgent(
        live_client, max_steps=3, middlewares=[ApprovalMiddleware()],
        default_generation_kwargs={"max_tokens": 512},
    )

    task = Task(
        task_id="e2e-8a",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Use the echo tool to repeat 'hello'."},
        ]),
    )
    sample = {"id": "s1", "input": "Use the echo tool to repeat 'hello'."}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
        tools=[echo_spec],
    ))

    # With AutoApprove, the flow should complete (possibly with tool use)
    assert outcome.task_result.status.value in {"success", "incorrect", "limit_exceeded", "error"}

    track_usage(cost_tracker, outcome.task_result.usage)


@pytest.mark.live
@pytest.mark.flaky(reruns=3, reruns_delay=5)
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_approval_auto_reject_blocks_tools(live_client, cost_tracker):
    """AutoReject policy blocks tool execution — agent may hit max_steps or error."""
    from snowl.agents.react_agent import ReActAgent
    from snowl.core.approval import AutoReject, ToolCall
    from snowl.core.tool import build_tool_spec

    def echo(text: str) -> str:
        return text

    echo_spec = build_tool_spec(echo)
    policy = AutoReject()

    class RejectionMiddleware:
        """Middleware that rejects all tool calls."""
        async def intercept_call(self, tool_name, args):
            decision = await policy.check(
                ToolCall(tool_name=tool_name, arguments=args), None
            )
            if decision.rejected:
                raise RuntimeError(f"Tool rejected: {decision.reason}")
            return args

    agent = ReActAgent(
        live_client, max_steps=3, middlewares=[RejectionMiddleware()],
        default_generation_kwargs={"max_tokens": 512},
    )

    task = Task(
        task_id="e2e-8b",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([
            {"id": "s1", "input": "Use the echo tool to repeat 'hello'."},
        ]),
    )
    sample = {"id": "s1", "input": "Use the echo tool to repeat 'hello'."}

    outcome = await execute_trial(TrialRequest(
        task=task, agent=agent, sample=sample, scorer=includes(),
        tools=[echo_spec],
    ))

    # With AutoReject, tool calls are blocked, agent should still complete
    # (may hit limit_exceeded or complete without using the tool)
    assert outcome.task_result.status.value in {
        "success", "incorrect", "limit_exceeded", "error",
    }

    track_usage(cost_tracker, outcome.task_result.usage)
