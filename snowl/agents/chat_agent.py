"""Built-in ChatAgent baseline implementation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from snowl.core.agent import AgentContext, AgentState, Observation, StopReason
from snowl.model import OpenAICompatibleChatClient


@dataclass
class ChatAgent:
    """Single-call baseline agent using an OpenAI-compatible chat endpoint."""

    model_client: OpenAICompatibleChatClient
    agent_id: str = "chat_agent"
    default_generation_kwargs: dict[str, Any] = field(default_factory=dict)

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState:
        # ChatAgent is intentionally no-tool for MVP baseline.
        _ = tools

        emit = context.metadata.get("__snowl_emit_event")
        started = int(time.time() * 1000)
        if callable(emit):
            emit(
                {
                    "event": "runtime.model.query.start",
                    "phase": "agent",
                    "agent_id": self.agent_id,
                    "task_id": context.task_id,
                    "sample_id": context.sample_id,
                }
            )
        response = await self.model_client.generate(
            list(state.messages),
            **self.default_generation_kwargs,
        )
        if callable(emit):
            emit(
                {
                    "event": "runtime.model.query.finish",
                    "phase": "agent",
                    "agent_id": self.agent_id,
                    "task_id": context.task_id,
                    "sample_id": context.sample_id,
                    "duration_ms": response.timing.duration_ms,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            )

        assistant_message: Mapping[str, Any] = {
            "role": response.message.get("role", "assistant"),
            "content": response.message.get("content", ""),
        }
        state.messages.append(assistant_message)

        trace_event = {
            "event": "chat_agent.generate",
            "agent_id": self.agent_id,
            "task_id": context.task_id,
            "sample_id": context.sample_id,
            "started_at_ms": started,
            "ended_at_ms": response.timing.ended_at_ms,
            "duration_ms": response.timing.duration_ms,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

        existing_traces = list((state.output or {}).get("trace_events", []))
        existing_traces.append(trace_event)

        state.output = {
            "message": dict(response.message),
            "raw": response.raw,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "timing": {
                "started_at_ms": response.timing.started_at_ms,
                "ended_at_ms": response.timing.ended_at_ms,
                "duration_ms": response.timing.duration_ms,
            },
            "trace_events": existing_traces,
        }

        state.observations.append(
            Observation(
                observation_type="model_response",
                payload={"role": assistant_message["role"]},
            )
        )
        state.stop_reason = StopReason.COMPLETED
        return state
