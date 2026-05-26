"""generate() Solver: the default model-calling Solver with tool-use loop.

Reference:
- ``references/inspect_ai/src/inspect_ai/solver/_solver.py`` (generate function)
- ``references/inspect_ai/src/inspect_ai/solver/_basic_agent.py`` (tool loop)
- ``snowl/snowl/agents/react_agent.py`` (existing ReAct loop, adapted)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from snowl.core.agent import Action, AgentContext, AgentState, Observation, StopReason
from snowl.core.solver import Generate as GenerateType
from snowl.core.solver import Solver
from snowl.core.tool import ToolSpec
from snowl.model.base import ChatModelClient
from snowl.tools.middleware import MiddlewareChain


class GenerateSolver:
    """Default Solver that calls the model with a tool-use loop.

    This Solver reads tools and middleware from ``state.output["_solver_tools"]``
    and ``state.output["_solver_middleware"]``, then runs a ReAct-style loop:
    call model -> parse tool calls -> execute tools -> feed results back.

    If no tools are registered, it performs a single model call.

    The ``generate`` parameter is **not** used by this Solver — it calls
    the model directly via ``model_client``.  This mirrors Inspect AI's
    ``generate()`` solver which also directly interacts with the model API.
    """

    solver_id: str = "generate"

    def __init__(
        self,
        model_client: ChatModelClient,
        *,
        max_steps: int = 8,
        temperature: float = 0.2,
        enable_json_fallback: bool = True,
        native_tool_call_policy: str = "single",
        generation_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model_client = model_client
        self.max_steps = max_steps
        self.temperature = temperature
        self.enable_json_fallback = enable_json_fallback
        self.native_tool_call_policy = native_tool_call_policy
        self.generation_kwargs = generation_kwargs or {}

    async def __call__(self, state: AgentState, generate: GenerateType) -> AgentState:
        # Extract tools and middleware from named attributes
        tool_specs: list[ToolSpec] = list(state.solver_tools or [])
        middlewares: list[Any] = list(state.solver_middleware or [])
        middleware_chain = MiddlewareChain(middlewares) if middlewares else None

        # Extract emit function from solver context for event parity with ReActAgent
        emit = None
        solver_context = state.solver_context
        if solver_context is not None and hasattr(solver_context, "metadata"):
            emit = solver_context.metadata.get("__snowl_emit_event")

        tool_map = {spec.name: spec.callable for spec in tool_specs}
        tool_schemas = [spec.to_openai_tool() for spec in tool_specs]
        allowed_tool_names = {spec.name for spec in tool_specs}

        messages: list[dict[str, Any]] = [dict(m) for m in state.messages]

        trace_events: list[dict[str, Any]] = list(
            (state.output or {}).get("trace_events", [])
        )
        usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        mode = "native_tools"

        for step in range(1, self.max_steps + 1):
            started = int(time.time() * 1000)

            # Call model
            kwargs = dict(self.generation_kwargs)
            kwargs.setdefault("temperature", self.temperature)
            if tool_schemas:
                kwargs["tools"] = tool_schemas
                kwargs.setdefault("tool_choice", "auto")

            response = None
            if mode == "native_tools":
                try:
                    if callable(emit):
                        emit({
                            "event": "runtime.model.query.start",
                            "phase": "solver",
                            "step": step,
                            "mode": mode,
                            "message": "waiting for provider response",
                        })
                    response = await self.model_client.generate(messages, **kwargs)
                    if callable(emit):
                        emit({
                            "event": "runtime.model.query.finish",
                            "phase": "solver",
                            "step": step,
                            "mode": mode,
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "total_tokens": response.usage.total_tokens,
                        })
                except Exception:
                    if callable(emit):
                        emit({
                            "event": "runtime.model.query.error",
                            "phase": "solver",
                            "step": step,
                            "mode": mode,
                            "message": "provider error, enabling JSON fallback",
                        })
                    if not self.enable_json_fallback:
                        raise
                    mode = "json_fallback"

            if mode == "json_fallback" and response is None:
                # Remove tools from kwargs for JSON fallback
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                if callable(emit):
                    emit({
                        "event": "runtime.model.query.start",
                        "phase": "solver",
                        "step": step,
                        "mode": mode,
                        "message": "waiting for provider response (json_fallback)",
                    })
                response = await self.model_client.generate(messages, **kwargs)
                if callable(emit):
                    emit({
                        "event": "runtime.model.query.finish",
                        "phase": "solver",
                        "step": step,
                        "mode": mode,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    })

            # Accumulate usage
            usage_total["input_tokens"] += response.usage.input_tokens
            usage_total["output_tokens"] += response.usage.output_tokens
            usage_total["total_tokens"] += response.usage.total_tokens

            message: dict[str, Any] = dict(response.message)

            trace_events.append({
                "event": "solver.generate.step",
                "step": step,
                "mode": mode,
                "started_at_ms": started,
                "ended_at_ms": response.timing.ended_at_ms,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            })

            # JSON fallback mode
            if mode == "json_fallback":
                content = str(message.get("content", "") or "")
                parsed = self._parse_json_action(content)
                if parsed is None:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "system",
                        "content": "FORMAT ERROR: Output must be a single valid JSON object.",
                    })
                    continue

                action_type = parsed.get("type")
                if action_type == "final":
                    final_message = {"role": "assistant", "content": str(parsed.get("answer", ""))}
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
                    messages.append({
                        "role": "system",
                        "content": "FORMAT ERROR: JSON.type must be 'tool_call' or 'final'.",
                    })
                    continue

                tool_name = str(parsed.get("tool", ""))
                arguments = parsed.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                raw_args = json.dumps(arguments, ensure_ascii=False)

                tool_result = await self._execute_tool_call(
                    tool_name, raw_args, tool_map, allowed_tool_names, middleware_chain
                )
                state.actions.append(Action(
                    action_type="tool_call",
                    payload={"tool_name": tool_name, "arguments": raw_args},
                ))
                state.observations.append(Observation(
                    observation_type="tool_result",
                    payload={"tool_name": tool_name, "result": tool_result},
                ))
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "system", "content": f"OBSERVATION: {tool_result}"})
                continue

            # Native tool calling mode
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                # No tool calls — agent is done
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

            calls_to_execute = (
                tool_calls if self.native_tool_call_policy == "all" else tool_calls[:1]
            )
            messages.append(message)
            for tool_call in calls_to_execute:
                fn = (tool_call.get("function") or {}).get("name", "")
                raw_args = (tool_call.get("function") or {}).get("arguments", "{}")
                state.actions.append(Action(
                    action_type="tool_call",
                    payload={
                        "tool_name": fn,
                        "tool_call_id": tool_call.get("id"),
                        "arguments": raw_args,
                    },
                ))

                result = await self._execute_tool_call(
                    fn, raw_args, tool_map, allowed_tool_names, middleware_chain
                )
                state.observations.append(Observation(
                    observation_type="tool_result",
                    payload={"tool_name": fn, "result": result},
                ))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(result),
                })

        # Max steps reached
        state.stop_reason = StopReason.MAX_STEPS
        state.messages = messages
        state.output = {
            "message": messages[-1] if messages else {},
            "usage": usage_total,
            "trace_events": trace_events,
            "error": "max_steps reached without final answer",
        }
        return state

    async def _execute_tool_call(
        self,
        tool_name: str,
        raw_arguments: str,
        tool_map: Mapping[str, Callable[..., Any]],
        allowed_tool_names: set[str],
        middleware_chain: MiddlewareChain | None = None,
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

        if middleware_chain is not None:
            parsed_args = await middleware_chain.run_call(tool_name, parsed_args)

        result = tool_fn(**parsed_args)
        if hasattr(result, "__await__"):
            result = await result

        if middleware_chain is not None:
            result = await middleware_chain.run_result(tool_name, parsed_args, result)

        return result

    def _parse_json_action(self, content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def generate(
    model_client: ChatModelClient,
    *,
    max_steps: int = 8,
    temperature: float = 0.2,
    enable_json_fallback: bool = True,
    native_tool_call_policy: str = "single",
    generation_kwargs: dict[str, Any] | None = None,
) -> GenerateSolver:
    """Create the default model-calling Solver with a tool-use loop.

    This Solver reads tools registered by ``use_tools()`` from
    ``state.output["_solver_tools"]`` and runs a ReAct-style loop.

    Args:
        model_client: The chat model client for making LLM calls.
        max_steps: Maximum number of generate-execute iterations.
        temperature: Sampling temperature.
        enable_json_fallback: Fall back to JSON action parsing on API error.
        native_tool_call_policy: "single" (first tool call per step) or "all".
        generation_kwargs: Extra kwargs passed to ``model_client.generate()``.

    Returns:
        A Solver that calls the model and resolves tool calls.
    """
    return GenerateSolver(
        model_client,
        max_steps=max_steps,
        temperature=temperature,
        enable_json_fallback=enable_json_fallback,
        native_tool_call_policy=native_tool_call_policy,
        generation_kwargs=generation_kwargs,
    )
