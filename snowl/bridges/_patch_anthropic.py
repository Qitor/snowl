"""Anthropic SDK monkey-patch for bridge mode.

Framework role:
- Patches ``anthropic._base_client.AsyncAPIClient.request`` to intercept
  model calls and redirect them through Snowl's ChatModelClient when bridge is active.
- Patch is installed once (lazily) and toggled via ContextVar.
- When bridge is not active, the original method is called with zero overhead.

Runtime/usage wiring:
- Called by ``snowl_bridge()`` to install the patch if Anthropic SDK is present.
- ``unpatch_anthropic()`` restores the original method.

Change guardrails:
- Must not import anthropic at module level (lazy import in functions).
- Must handle any anthropic SDK version gracefully (try/except on patch install).
"""

from __future__ import annotations

import functools
import time
from typing import Any

_original_anthropic_request: Any = None
_patched_anthropic: bool = False


def patch_anthropic() -> None:
    """Install the Anthropic SDK patch (idempotent)."""
    global _original_anthropic_request, _patched_anthropic
    if _patched_anthropic:
        return

    try:
        from anthropic._base_client import AsyncAPIClient
    except ImportError:
        return  # Anthropic SDK not installed

    _original_anthropic_request = getattr(AsyncAPIClient, "request", None)
    if _original_anthropic_request is None:
        return

    @functools.wraps(_original_anthropic_request)
    async def _patched_request(self: AsyncAPIClient, *args: Any, **kwargs: Any) -> Any:
        from snowl.bridges._config import get_bridge_config

        config = get_bridge_config()
        if config is None or not config.enabled or config.model_client is None:
            return await _original_anthropic_request(self, *args, **kwargs)

        # Try to intercept the request if it's a messages request
        try:
            return await _handle_anthropic_request(self, config, *args, **kwargs)
        except Exception:
            # If interception fails, fall back to original
            return await _original_anthropic_request(self, *args, **kwargs)

    try:
        AsyncAPIClient.request = _patched_request
        _patched_anthropic = True
    except Exception:
        pass  # Cannot patch (frozen class, etc.)


async def _handle_anthropic_request(
    client: Any,
    config: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Handle an intercepted Anthropic request through the bridge."""
    from snowl.bridges._config import record_model_call

    # Extract request details from the options parameter
    try:
        options = args[1] if len(args) > 1 else kwargs.get("options")
        json_data = getattr(options, "json_data", None) if options else None
        url = getattr(options, "url", None) if options else None
    except Exception:
        json_data = None
        url = None

    if json_data is None or url not in ("/v1/messages", "/v1/messages?beta=true"):
        # Not a messages request, pass through
        return await _original_anthropic_request(client, *args, **kwargs)

    messages = json_data.get("messages", [])
    model_name = json_data.get("model", "unknown")

    # Convert Anthropic message format to generic format for Snowl
    generic_messages = _convert_anthropic_messages(messages, json_data.get("system"))

    # Call Snowl's model client
    started = int(time.time() * 1000)
    response = await config.model_client.generate(generic_messages)
    ended = int(time.time() * 1000)

    # Record usage
    usage = getattr(response, "usage", None)
    if usage is not None:
        record_model_call(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            duration_ms=max(0, ended - started),
            model=model_name,
        )

    # Convert ModelResponse to Anthropic Messages response format
    return _model_response_to_anthropic_message(response, model_name)


def _convert_anthropic_messages(
    messages: list[dict[str, Any]],
    system: str | None = None,
) -> list[dict[str, Any]]:
    """Convert Anthropic message format to generic format."""
    result: list[dict[str, Any]] = []
    if system:
        result.append({"role": "system", "content": system})
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Anthropic content blocks → extract text
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            content = " ".join(text_parts) if text_parts else str(content)
        result.append({"role": role, "content": str(content)})
    return result


def _model_response_to_anthropic_message(response: Any, model_name: str) -> Any:
    """Convert a Snowl ModelResponse to an Anthropic Message object."""
    try:
        from anthropic.types import Message, Usage as AnthropicUsage, TextBlock

        message_obj = getattr(response, "message", None)
        content_text = ""
        if message_obj is not None:
            content_text = str(getattr(message_obj, "content", message_obj))

        usage_obj = getattr(response, "usage", None)
        input_tokens = 0
        output_tokens = 0
        if usage_obj is not None:
            input_tokens = getattr(usage_obj, "input_tokens", 0) or 0
            output_tokens = getattr(usage_obj, "output_tokens", 0) or 0

        return Message(
            id=f"msg_snowl_bridge_{id(response)}",
            type="message",
            role="assistant",
            content=[TextBlock(type="text", text=content_text)],
            model=model_name,
            stop_reason="end_turn",
            stop_sequence=None,
            usage=AnthropicUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )
    except ImportError:
        # Anthropic types not available; return a dict-like object
        return _DictAnthropicMessage(response, model_name)


class _DictAnthropicMessage:
    """Fallback Message-like object when anthropic types aren't available."""

    def __init__(self, response: Any, model_name: str) -> None:
        message_obj = getattr(response, "message", None)
        self.content = ""
        if message_obj is not None:
            self.content = str(getattr(message_obj, "content", message_obj))
        self.model = model_name
        self.id = f"msg_snowl_bridge_{id(response)}"
        self.type = "message"
        self.role = "assistant"
        self.stop_reason = "end_turn"


def unpatch_anthropic() -> None:
    """Restore the original Anthropic SDK method."""
    global _original_anthropic_request, _patched_anthropic
    if not _patched_anthropic or _original_anthropic_request is None:
        return
    try:
        from anthropic._base_client import AsyncAPIClient
        AsyncAPIClient.request = _original_anthropic_request
    except ImportError:
        pass
    _original_anthropic_request = None
    _patched_anthropic = False
