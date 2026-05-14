"""Convert a serialized trial outcome into OpenAI-compatible conversation format.

Framework role:
- Produces a portable ``{"messages": [...]}`` representation of agent execution
  that matches the OpenAI Chat Completions API message schema.
- Enables replay, compliance audit, and analysis with standard tooling.

Runtime/usage wiring:
- Called by ``snowl export --format openai`` and the WebUI export endpoint.

Change guardrails:
- Output schema must remain compatible with OpenAI chat message types.
"""

from __future__ import annotations

import json
from typing import Any


def outcome_to_openai_conversation(outcome: dict[str, Any]) -> dict[str, Any]:
    """Convert a serialized trial outcome to OpenAI chat messages format.

    Args:
        outcome: A serialized trial outcome dict with keys:
            ``task_result``, ``scores``, ``trace``, etc.

    Returns:
        Dict with keys:
            ``trial_key``, ``task_id``, ``model``, ``messages``, ``scores``, ``status``.
            The ``messages`` list follows the OpenAI Chat Completions API schema.
    """
    task_result = outcome.get("task_result", {}) or {}
    trace = outcome.get("trace", {}) or {}
    scores = outcome.get("scores", {}) or {}

    task_id = str(task_result.get("task_id", ""))
    agent_id = str(task_result.get("agent_id", ""))
    sample_id = str(task_result.get("sample_id", ""))
    variant_id = ""
    payload = task_result.get("payload", {}) or {}
    if isinstance(payload, dict):
        variant_id = str(payload.get("variant_id", ""))

    trial_key_parts = [task_id, agent_id, variant_id, sample_id]
    trial_key = "::".join(part for part in trial_key_parts if part)

    sample_input = task_result.get("sample_input")
    final_output = task_result.get("final_output")

    # Extract model name from first model_io event or trace
    model = _extract_model(trace, task_result)

    messages = _build_messages(sample_input, trace, final_output)

    # Build scores summary
    scores_summary: dict[str, Any] = {}
    for key, value in scores.items():
        if isinstance(value, dict) and "value" in value:
            scores_summary[key] = value["value"]
        else:
            scores_summary[key] = value

    return {
        "trial_key": trial_key,
        "task_id": task_id,
        "model": model,
        "messages": messages,
        "scores": scores_summary,
        "status": str(task_result.get("status", "unknown")),
    }


def _extract_model(trace: dict[str, Any], task_result: dict[str, Any]) -> str:
    """Extract the model name from trace events or task result."""
    # Try trace_events first
    trace_events = trace.get("trace_events", []) or []
    for event in trace_events:
        if isinstance(event, dict):
            model = str(event.get("model", "")).strip()
            if model:
                return model

    # Try actions for model info
    actions = trace.get("actions", []) or []
    for action in actions:
        if isinstance(action, dict):
            payload = action.get("payload", {}) or {}
            model = str(payload.get("model", "")).strip()
            if model:
                return model

    return ""


def _build_messages(
    sample_input: Any,
    trace: dict[str, Any],
    final_output: Any,
) -> list[dict[str, Any]]:
    """Build the OpenAI-compatible messages list from trace data."""
    messages: list[dict[str, Any]] = []

    # 1. System + user messages from sample_input
    _add_input_messages(messages, sample_input)

    # 2. Step-by-step: assistant (thought + tool_calls) → tool (results)
    actions = trace.get("actions", []) or []
    observations = trace.get("observations", []) or []

    for i, raw_action in enumerate(actions):
        if not isinstance(raw_action, dict):
            continue

        action_payload = raw_action.get("payload", {}) or {}
        if not isinstance(action_payload, dict):
            action_payload = {}

        action_type = str(raw_action.get("action_type", "")).strip()

        # Build assistant message
        assistant_msg: dict[str, Any] = {"role": "assistant"}

        # Extract thought/content from the action context
        thought = str(action_payload.get("thought", "")).strip()
        if not thought:
            thought = str(action_payload.get("reasoning", "")).strip()

        # Extract tool calls
        tool_name = str(action_payload.get("tool_name", action_payload.get("name", ""))).strip()
        raw_args = action_payload.get("arguments", action_payload.get("args", {}))

        if action_type == "tool_call" or tool_name:
            # Has tool call
            if thought:
                assistant_msg["content"] = thought

            call_id = str(action_payload.get("tool_call_id", f"call_{i + 1}"))
            tool_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": _serialize_arguments(raw_args),
                },
            }
            assistant_msg["tool_calls"] = [tool_call]
        elif thought:
            assistant_msg["content"] = thought
        else:
            # Generic action — just record it
            assistant_msg["content"] = f"[{action_type}]" if action_type else "[action]"

        messages.append(assistant_msg)

        # Build corresponding tool result message
        if i < len(observations):
            raw_obs = observations[i]
            if isinstance(raw_obs, dict):
                obs_payload = raw_obs.get("payload", {}) or {}
                if not isinstance(obs_payload, dict):
                    obs_payload = {}
                result = obs_payload.get("result", obs_payload.get("content", ""))
                call_id = str(action_payload.get("tool_call_id", f"call_{i + 1}"))

                tool_msg: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _serialize_result(result),
                }
                messages.append(tool_msg)

    # 3. Final assistant answer
    if final_output is not None:
        final_text = _extract_final_text(final_output)
        if final_text:
            # Only add if it's different from the last assistant message
            last_assistant = None
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    last_assistant = msg
                    break
            if last_assistant is None or last_assistant.get("content", "") != final_text:
                messages.append({"role": "assistant", "content": final_text})

    return messages


def _add_input_messages(messages: list[dict[str, Any]], sample_input: Any) -> None:
    """Extract system and user messages from sample_input."""
    if sample_input is None:
        return

    if isinstance(sample_input, str):
        messages.append({"role": "user", "content": sample_input})
        return

    if isinstance(sample_input, dict):
        # Check for messages-style input
        input_messages = sample_input.get("messages")
        if isinstance(input_messages, list):
            for msg in input_messages:
                if isinstance(msg, dict):
                    role = str(msg.get("role", "user")).strip().lower()
                    content = msg.get("content", "")
                    if role in ("system", "user", "assistant"):
                        messages.append({"role": role, "content": content})
            return

        # Check for individual fields
        system = sample_input.get("system_prompt") or sample_input.get("system")
        if system and isinstance(system, str):
            messages.append({"role": "system", "content": system})

        question = (
            sample_input.get("question")
            or sample_input.get("query")
            or sample_input.get("prompt")
            or sample_input.get("instruction")
            or sample_input.get("input")
            or sample_input.get("user_input")
        )
        if question and isinstance(question, str):
            messages.append({"role": "user", "content": question})
            return

        # Fallback: serialize the whole thing as user message
        messages.append({"role": "user", "content": json.dumps(sample_input, ensure_ascii=False)})
        return

    # Fallback for any other type
    messages.append({"role": "user", "content": str(sample_input)})


def _extract_final_text(final_output: Any) -> str:
    """Extract text from the final output."""
    if isinstance(final_output, str):
        return final_output

    if isinstance(final_output, dict):
        content = final_output.get("content")
        if isinstance(content, str):
            return content

        message = final_output.get("message")
        if isinstance(message, dict):
            msg_content = message.get("content")
            if isinstance(msg_content, str):
                return msg_content

        answer = final_output.get("answer") or final_output.get("response") or final_output.get("output")
        if isinstance(answer, str):
            return answer

    return ""


def _serialize_arguments(raw: Any) -> str:
    """Serialize tool call arguments to a JSON string."""
    if isinstance(raw, str):
        # Validate it's valid JSON
        try:
            json.loads(raw)
            return raw
        except (json.JSONDecodeError, TypeError):
            pass
        return json.dumps({"raw": raw})
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    if raw is None:
        return "{}"
    return json.dumps({"value": raw}, ensure_ascii=False)


def _serialize_result(result: Any) -> str:
    """Serialize a tool result to a string."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(result)
