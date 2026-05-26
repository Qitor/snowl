"""Multi-step task executor for sequential evaluation with per-step scoring.

Framework role:
- Executes a multi-step Task by iterating through ``Task.steps`` sequentially.
- Each step gets its own instruction injected, agent execution, and optional scoring.
- Early exit when a step's score falls below ``min_reward``.

Runtime/usage wiring:
- Called by the engine when a Task has non-empty ``steps``.
- Produces a list of ``StepResult`` objects stored in ``TaskResult.step_results``.

Change guardrails:
- Single-step Tasks (``steps=()``) are completely unaffected.
- Step isolation: each step sees accumulated messages from prior steps.

Reference: ``references/harbor/src/harbor/trial/multi_step.py`` (MultiStepTrial._run)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from snowl.core.agent import Agent, AgentContext, AgentState, StopReason
from snowl.core.step import TaskStep
from snowl.core.task import Task
from snowl.core.task_result import StepResult, TaskStatus, Timing, Usage
from snowl.core.tool import ToolSpec


@dataclass
class MultiStepExecutor:
    """Execute a multi-step task, running each step sequentially with scoring."""

    async def execute(
        self,
        task: Task,
        agent: Agent,
        sample: dict[str, Any],
        context: AgentContext,
        tools: Sequence[ToolSpec] | None = None,
        agents_map: dict[str, Agent] | None = None,
    ) -> list[StepResult]:
        """Execute all steps in order, early-exiting on min_reward failure.

        Args:
            task: The Task containing steps to execute.
            agent: The default Agent to run for each step.
            sample: The sample data for this trial.
            context: The agent execution context.
            tools: Available tools for the agent.
            agents_map: Optional mapping of agent_id -> Agent for per-step overrides.

        Returns:
            List of StepResult, one per executed step.
        """
        results: list[StepResult] = []
        state = AgentState(
            messages=[], actions=[], observations=[], output=None, stop_reason=None,
        )

        # Inject the initial user message from the sample
        user_input = sample.get("input") or sample.get("instruction") or ""
        if user_input:
            state.messages.append({"role": "user", "content": str(user_input)})

        for i, step in enumerate(task.steps):
            # Resolve agent: use step override if specified, else default
            step_agent = agent
            if step.agent_override and agents_map:
                override = agents_map.get(step.agent_override)
                if override is not None:
                    step_agent = override

            step_result = await self._execute_step(
                step=step,
                step_index=i,
                state=state,
                agent=step_agent,
                context=context,
                tools=tools,
            )
            results.append(step_result)

            # Check min_reward threshold
            if step_result.max_score < step.min_reward:
                # Mark remaining steps as skipped
                break

            # Carry forward: keep messages, reset stop_reason for next step
            state.stop_reason = None

        return results

    async def _execute_step(
        self,
        step: TaskStep,
        step_index: int,
        state: AgentState,
        agent: Agent,
        context: AgentContext,
        tools: Sequence[ToolSpec] | None = None,
    ) -> StepResult:
        """Execute a single step and return its result."""
        # Inject step instruction as a user message
        state.messages.append({"role": "user", "content": step.instruction})

        started_ms = int(time.time() * 1000)

        try:
            state = await agent.run(state, context, tools=tools)
            ended_ms = int(time.time() * 1000)

            status = _step_status_from_stop_reason(state.stop_reason)
            output = state.output or {}
            usage_data = output.get("usage") or {}

            return StepResult(
                step_id=step.step_id,
                status=status,
                scores={},
                max_score=0.0,
                timing=Timing(
                    started_at_ms=started_ms,
                    ended_at_ms=ended_ms,
                    duration_ms=ended_ms - started_ms,
                ),
                usage=Usage(
                    input_tokens=int(usage_data.get("input_tokens", 0) or 0),
                    output_tokens=int(usage_data.get("output_tokens", 0) or 0),
                    total_tokens=int(usage_data.get("total_tokens", 0) or 0),
                ),
                artifacts={},
            )
        except Exception as exc:
            ended_ms = int(time.time() * 1000)
            return StepResult(
                step_id=step.step_id,
                status=TaskStatus.ERROR,
                scores={},
                max_score=0.0,
                timing=Timing(
                    started_at_ms=started_ms,
                    ended_at_ms=ended_ms,
                    duration_ms=ended_ms - started_ms,
                ),
                artifacts={"error": str(exc)},
            )


def _step_status_from_stop_reason(stop_reason: StopReason | None) -> TaskStatus:
    """Map StopReason to TaskStatus for step results."""
    if stop_reason is None or stop_reason == StopReason.COMPLETED:
        return TaskStatus.SUCCESS
    if stop_reason == StopReason.MAX_STEPS:
        return TaskStatus.LIMIT_EXCEEDED
    if stop_reason == StopReason.LIMIT_EXCEEDED:
        return TaskStatus.LIMIT_EXCEEDED
    if stop_reason == StopReason.ERROR:
        return TaskStatus.ERROR
    return TaskStatus.SUCCESS
