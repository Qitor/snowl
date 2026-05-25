"""Snowl Bridge Mode -- intercept third-party SDK calls and route through Snowl's model client.

Framework role:
- Provides ``snowl_bridge()`` async context manager that activates bridge mode.
- When active, OpenAI/Anthropic SDK calls from third-party agent code
  are intercepted and routed through Snowl's ChatModelClient.
- Usage tracking is automatically recorded into a ``BridgeUsageAccumulator``.

Runtime/usage wiring:
- Used by the engine when ``eval.bridge.enabled`` is true in project.yml.
- Can also be used standalone for testing third-party agent integration.

Change guardrails:
- Bridge patches are installed once and toggled via ContextVar (no global state).
- When bridge is not active, patched methods pass through with zero overhead.
- Must not import from snowl.core at module level to avoid circular imports.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from snowl.bridges._config import (
    BridgeConfig,
    BridgeUsageAccumulator,
    get_bridge_config,
    set_bridge_config,
    reset_bridge_config,
    set_usage_accumulator,
    reset_usage_accumulator,
)


@asynccontextmanager
async def snowl_bridge(
    *,
    model_client: Any,
    provider_id: str = "default",
    patch_openai: bool = True,
    patch_anthropic: bool = True,
):
    """Async context manager that activates bridge mode.

    While active, OpenAI/Anthropic SDK calls from third-party agent code
    are intercepted and routed through Snowl's ``model_client``.

    Usage::

        async with snowl_bridge(model_client=my_client) as bridge:
            result = await third_party_agent.run(...)
            usage = bridge.usage()

    Args:
        model_client: A ChatModelClient-compatible object.
        provider_id: Identifier for the model provider (for logging).
        patch_openai: Whether to patch the OpenAI SDK (if installed).
        patch_anthropic: Whether to patch the Anthropic SDK (if installed).
    """
    # Install patches (idempotent — safe to call multiple times)
    if patch_openai:
        from snowl.bridges._patch_openai import patch_openai as _patch_o
        _patch_o()
    if patch_anthropic:
        from snowl.bridges._patch_anthropic import patch_anthropic as _patch_a
        _patch_a()

    # Set bridge config via ContextVar
    config = BridgeConfig(
        enabled=True,
        model_client=model_client,
        provider_id=provider_id,
    )
    config_token = set_bridge_config(config)

    # Create usage accumulator
    accumulator = BridgeUsageAccumulator()
    usage_token = set_usage_accumulator(accumulator)

    class BridgeHandle:
        """Handle returned by snowl_bridge() for querying bridge state."""

        def usage(self) -> dict[str, Any]:
            """Return accumulated usage statistics."""
            return {
                "call_count": accumulator.call_count,
                "input_tokens": accumulator.input_tokens,
                "output_tokens": accumulator.output_tokens,
                "total_tokens": accumulator.total_tokens,
                "call_timings_ms": list(accumulator.call_timings_ms),
            }

    try:
        yield BridgeHandle()
    finally:
        # Clear ContextVar — patches will pass through on next call
        reset_bridge_config(config_token)
        reset_usage_accumulator(usage_token)
