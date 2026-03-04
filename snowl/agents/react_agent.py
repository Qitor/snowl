"""Built-in ReActAgent implementation with native tools + JSON fallback."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from snowl.core.agent import Action, AgentContext, AgentState, Observation, StopReason
from snowl.core.tool import ToolSpec, resolve_tool_spec
from snowl.model import OpenAICompatibleChatClient


ToolCallable = Callable[..., Any]
SYSTEM_PROMPT_TEMPLATE = """You are a Reasoning & Acting (ReAct) agent.

You solve the user's task by iterating:
Plan -> Act (call a tool) -> Observe -> Update plan ...
Repeat until you can provide a final answer.

========================
TOOL SCHEMA (INJECTED AT RUNTIME)
{tool_schema}
========================

IMPORTANT FOR THE CODING AGENT IMPLEMENTING THIS SYSTEM:
- The placeholder "{tool_schema}" MUST be replaced at runtime with the actual tool definitions (names, descriptions, and JSON argument schemas).
- The controller MUST pass this system prompt (with "{tool_schema}" filled) into the LLM request.
- You may ONLY call tools that appear in the injected tool schema.

## Preferred Tool Calling
If the API supports native tool calling, request tools via the API's "tools" parameter and use tool calls in your response when needed.

## Fallback (JSON Action Protocol)
If native tool calling is not available, you MUST output a single JSON object with either:
(A) tool_call  { "type":"tool_call", "tool":"...", "arguments":{...} }
(B) final      { "type":"final", "answer":"..." }
The controller will execute the tool and provide the Observation back.

## Behavioral Rules
- Use tools whenever needed to get real data or perform actions. Do NOT fabricate tool outputs.
- Call at most ONE tool per step (one action at a time). Wait for the tool result before proceeding.
- If you have enough information, provide the final answer immediately.
- Keep the final answer concise and directly helpful.
"""


@dataclass
class ReActAgent:
    """ReAct loop with tool-schema injection and dual execution modes."""

    model_client: OpenAICompatibleChatClient
    agent_id: str = "react_agent"
    max_steps: int = 8
    temperature: float = 0.2
    default_generation_kwargs: dict[str, Any] = field(default_factory=dict)
    system_prompt_template: str = SYSTEM_PROMPT_TEMPLATE
    enable_json_fallback: bool = True

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState:
        emit = context.metadata.get("__snowl_emit_event")

        async def _generate_with_events(messages: list[dict[str, Any]], **kwargs: Any):
            start_ms = int(time.time() * 1000)
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
            response = await self.model_client.generate(messages, **kwargs)
            if callable(emit):
                emit(
                    {
                        "event": "runtime.model.query.finish",
                        "phase": "agent",
                        "agent_id": self.agent_id,
                        "task_id": context.task_id,
                        "sample_id": context.sample_id,
                        "duration_ms": max(0, int(response.timing.ended_at_ms) - start_ms),
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                )
            return response

        tool_map = self._build_tool_map(tools)
        tool_schemas = self._build_openai_tool_schemas(tools)
        allowed_tool_names = {schema["function"]["name"] for schema in tool_schemas}
        system_prompt = self.build_system_prompt(tool_schemas)

        messages: list[dict[str, Any]] = [dict(m) for m in state.messages]
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages[0] = {"role": "system", "content": system_prompt}

        trace_events = list((state.output or {}).get("trace_events", []))
        usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        mode = "native_tools"

        for step in range(1, self.max_steps + 1):
            started = int(time.time() * 1000)
            response = None
            if mode == "native_tools":
                try:
                    kwargs = dict(self.default_generation_kwargs)
                    kwargs.setdefault("temperature", self.temperature)
                    if tool_schemas:
                        kwargs["tools"] = tool_schemas
                        kwargs.setdefault("tool_choice", "auto")
                    response = await _generate_with_events(messages, **kwargs)
                except Exception as exc:
                    if not self.enable_json_fallback:
                        raise
                    mode = "json_fallback"
                    trace_events.append(
                        {
                            "event": "react_agent.fallback_enabled",
                            "agent_id": self.agent_id,
                            "task_id": context.task_id,
                            "sample_id": context.sample_id,
                            "step": step,
                            "reason": str(exc),
                        }
                    )

            if mode == "json_fallback" and response is None:
                kwargs = dict(self.default_generation_kwargs)
                kwargs.setdefault("temperature", self.temperature)
                response = await _generate_with_events(messages, **kwargs)

            usage_total["input_tokens"] += response.usage.input_tokens
            usage_total["output_tokens"] += response.usage.output_tokens
            usage_total["total_tokens"] += response.usage.total_tokens

            message: dict[str, Any] = dict(response.message)

            trace_events.append(
                {
                    "event": "react_agent.step",
                    "agent_id": self.agent_id,
                    "task_id": context.task_id,
                    "sample_id": context.sample_id,
                    "step": step,
                    "mode": mode,
                    "started_at_ms": started,
                    "ended_at_ms": response.timing.ended_at_ms,
                    "duration_ms": response.timing.duration_ms,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                }
            )

            if mode == "json_fallback":
                content = str(message.get("content", "") or "")
                parsed = self._parse_json_action(content)
                if parsed is None:
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "FORMAT ERROR: Output must be a single valid JSON object. Try again."
                            ),
                        }
                    )
                    continue

                action_type = parsed.get("type")
                if action_type == "final":
                    final_message = {
                        "role": "assistant",
                        "content": str(parsed.get("answer", "")),
                    }
                    messages.append(final_message)
                    state.messages = messages
                    state.stop_reason = StopReason.COMPLETED
                    state.output = {
                        "message": final_message,
                        "raw": response.raw,
                        "usage": usage_total,
                        "trace_events": trace_events,
                    }
                    return state

                if action_type != "tool_call":
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "system",
                            "content": "FORMAT ERROR: JSON.type must be 'tool_call' or 'final'.",
                        }
                    )
                    continue

                tool_name = str(parsed.get("tool", ""))
                arguments = parsed.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                raw_args = json.dumps(arguments, ensure_ascii=False)

                tool_result = await self._execute_tool_call(
                    tool_name, raw_args, tool_map, allowed_tool_names
                )
                state.actions.append(
                    Action(
                        action_type="tool_call",
                        payload={"tool_name": tool_name, "arguments": raw_args},
                    )
                )
                state.observations.append(
                    Observation(
                        observation_type="tool_result",
                        payload={"tool_name": tool_name, "result": tool_result},
                    )
                )
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "system",
                        "content": f"OBSERVATION: {tool_result}",
                    }
                )
                continue

            # native tool calling mode
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                messages.append(message)
                state.messages = messages
                state.stop_reason = StopReason.COMPLETED
                state.output = {
                    "message": message,
                    "raw": response.raw,
                    "usage": usage_total,
                    "trace_events": trace_events,
                }
                return state

            # ReAct rule: execute only one tool call per step.
            tool_call = tool_calls[0]
            fn = (tool_call.get("function") or {}).get("name", "")
            raw_args = (tool_call.get("function") or {}).get("arguments", "{}")
            action_payload = {
                "tool_name": fn,
                "tool_call_id": tool_call.get("id"),
                "arguments": raw_args,
            }
            state.actions.append(Action(action_type="tool_call", payload=action_payload))

            result = await self._execute_tool_call(fn, raw_args, tool_map, allowed_tool_names)
            state.observations.append(
                Observation(
                    observation_type="tool_result",
                    payload={"tool_name": fn, "result": result},
                )
            )

            # Keep assistant tool_call message then feed tool observation back.
            messages.append(message)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(result),
                }
            )

        state.stop_reason = StopReason.MAX_STEPS
        state.messages = messages
        state.output = {
            "message": messages[-1] if messages else {},
            "usage": usage_total,
            "trace_events": trace_events,
            "error": "max_steps reached without final answer",
        }
        return state

    def render_tool_schema_for_prompt(self, tools: Sequence[dict[str, Any]]) -> str:
        return json.dumps(list(tools), ensure_ascii=False, indent=2)

    def build_system_prompt(self, tools: Sequence[dict[str, Any]]) -> str:
        return self.system_prompt_template.replace(
            "{tool_schema}", self.render_tool_schema_for_prompt(tools)
        )

    def _build_tool_map(self, tools: Sequence[Any] | None) -> dict[str, ToolCallable]:
        if not tools:
            return {}

        tool_map: dict[str, ToolCallable] = {}
        for tool in tools:
            spec = resolve_tool_spec(tool)
            tool_map[spec.name] = spec.callable
        return tool_map

    def _build_openai_tool_schemas(self, tools: Sequence[Any] | None) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        if not tools:
            return schemas

        for tool in tools:
            spec: ToolSpec = resolve_tool_spec(tool)
            schemas.append(spec.to_openai_tool())
        return schemas

    async def _execute_tool_call(
        self,
        tool_name: str,
        raw_arguments: str,
        tool_map: Mapping[str, ToolCallable],
        allowed_tool_names: set[str],
    ) -> Any:
        if tool_name not in allowed_tool_names:
            return f"ERROR: unknown tool '{tool_name}'"

        tool_fn = tool_map.get(tool_name)
        if tool_fn is None:
            return f"Tool '{tool_name}' not found."

        try:
            parsed_args = json.loads(raw_arguments or "{}")
            if not isinstance(parsed_args, dict):
                parsed_args = {}
        except json.JSONDecodeError:
            parsed_args = {}

        result = tool_fn(**parsed_args)
        if hasattr(result, "__await__"):
            return await result
        return result

    def _parse_json_action(self, content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
