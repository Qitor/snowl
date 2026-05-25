"""Bridge-aware generate function for solver chains.

Framework role:
- Provides a ``Generate`` function that routes through Snowl's ChatModelClient
  when bridge mode is active, replacing the engine's ``_noop_generate``.

Runtime/usage wiring:
- Created by the engine when bridge mode is detected, passed to solver chains
  as the ``generate`` parameter.

Change guardrails:
- Must not import from snowl.core except for type references.
- Must handle model client errors gracefully.
"""

from __future__ import annotations

import time
from typing import Any

from snowl.core.agent import AgentState, StopReason
from snowl.core.solver import Generate


def bridge_generate(model_client: Any) -> Generate:
    """Create a generate function that uses the bridge's model client.

    This is the replacement for ``_noop_generate`` when bridge mode is enabled.
    It calls the model_client directly and records usage into the bridge accumulator.

    Args:
        model_client: A ChatModelClient-compatible object with ``generate()``.

    Returns:
        A ``Generate`` function suitable for passing to solver chains.
    """

    async def _generate(*args: Any, **gen_kwargs: Any) -> AgentState:
        from snowl.bridges._config import get_usage_accumulator, record_model_call

        # Extract state from args
        state: AgentState | None = None
        if args:
            state = args[0]
        if state is None and "state" in gen_kwargs:
            state = gen_kwargs.pop("state")

        if state is None:
            raise RuntimeError("bridge_generate requires an AgentState argument")

        # Build messages from state
        messages: list[dict[str, Any]] = []
        for msg in state.messages:
            if isinstance(msg, dict):
                messages.append(msg)
            elif hasattr(msg, "__dict__"):
                messages.append(vars(msg))
            else:
                messages.append({"role": "user", "content": str(msg)})

        # Call model client
        started = int(time.time() * 1000)
        response = await model_client.generate(messages, **gen_kwargs)
        ended = int(time.time() * 1000)

        # Record usage
        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None:
            record_model_call(
                input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
                duration_ms=max(0, ended - started),
            )

        # Update state with model response
        message_obj = getattr(response, "message", None)
        content = ""
        if message_obj is not None:
            content = str(getattr(message_obj, "content", message_obj))

        # Append assistant message
        state.messages.append({"role": "assistant", "content": content})

        # Update output
        output = dict(state.output) if state.output else {}
        output["message"] = {"role": "assistant", "content": content}
        if usage_obj is not None:
            output["usage"] = {
                "input_tokens": getattr(usage_obj, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage_obj, "output_tokens", 0) or 0,
                "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
            }
        state.output = output

        return state

    return _generate
