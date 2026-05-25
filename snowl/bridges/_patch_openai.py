"""OpenAI SDK monkey-patch for bridge mode.

Framework role:
- Patches ``openai.AsyncAPIClient._request`` to intercept model calls
  and redirect them through Snowl's ChatModelClient when bridge is active.
- Patch is installed once (lazily) and toggled via ContextVar.
- When bridge is not active, the original method is called with zero overhead.

Runtime/usage wiring:
- Called by ``snowl_bridge()`` to install the patch if OpenAI SDK is present.
- ``unpatch_openai()`` restores the original method.

Change guardrails:
- Must not import openai at module level (lazy import in functions).
- Must handle any openai SDK version gracefully (try/except on patch install).
"""

from __future__ import annotations

import functools
import time
from typing import Any

_original_openai_request: Any = None
_patched_openai: bool = False


def patch_openai() -> None:
    """Install the OpenAI SDK patch (idempotent)."""
    global _original_openai_request, _patched_openai
    if _patched_openai:
        return

    try:
        from openai._base_client import AsyncAPIClient
    except ImportError:
        return  # OpenAI SDK not installed

    _original_openai_request = getattr(AsyncAPIClient, "_request", None)
    if _original_openai_request is None:
        return

    @functools.wraps(_original_openai_request)
    async def _patched_request(self: AsyncAPIClient, *args: Any, **kwargs: Any) -> Any:
        from snowl.bridges._config import get_bridge_config

        config = get_bridge_config()
        if config is None or not config.enabled or config.model_client is None:
            return await _original_openai_request(self, *args, **kwargs)

        # Try to intercept the request if it's a chat completion
        try:
            return await _handle_openai_request(self, config, *args, **kwargs)
        except Exception:
            # If interception fails, fall back to original
            return await _original_openai_request(self, *args, **kwargs)

    try:
        AsyncAPIClient._request = _patched_request
        _patched_openai = True
    except Exception:
        pass  # Cannot patch (frozen class, etc.)


async def _handle_openai_request(
    client: Any,
    config: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Handle an intercepted OpenAI request through the bridge."""
    from snowl.bridges._config import record_model_call

    # Extract the request body from the build_request result
    # The _request method receives a built request; we need to extract
    # the URL path and JSON body to determine if this is a chat completion.
    # For simplicity, we intercept at a higher level using the response format.

    # Attempt to extract messages from the request
    # OpenAI SDK's _request gets cast_to, options, etc.
    # We'll check if options.json_data contains messages
    try:
        options = args[1] if len(args) > 1 else kwargs.get("options")
        json_data = getattr(options, "json_data", None) if options else None
        url = getattr(options, "url", None) if options else None
    except Exception:
        json_data = None
        url = None

    if json_data is None or url != "/chat/completions":
        # Not a chat completion request, pass through
        from snowl.bridges._patch_openai import _original_openai_request
        return await _original_openai_request(client, *args, **kwargs)

    messages = json_data.get("messages", [])
    model_name = json_data.get("model", "unknown")

    # Call Snowl's model client
    started = int(time.time() * 1000)
    response = await config.model_client.generate(messages)
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

    # Convert ModelResponse to OpenAI ChatCompletion format
    return _model_response_to_openai_completion(response, model_name)


def _model_response_to_openai_completion(response: Any, model_name: str) -> Any:
    """Convert a Snowl ModelResponse to an OpenAI ChatCompletion object."""
    try:
        from openai.types.chat import ChatCompletion, ChatCompletionMessage
        from openai.types.chat.chat_completion import Choice
        from openai.types.completion_usage import CompletionUsage

        # Extract content from response
        message_obj = getattr(response, "message", None)
        content = ""
        if message_obj is not None:
            content = getattr(message_obj, "content", str(message_obj))
            if isinstance(content, list):
                # Handle content blocks
                content = " ".join(
                    getattr(block, "text", str(block))
                    for block in content
                    if hasattr(block, "text") or isinstance(block, str)
                )

        usage_obj = getattr(response, "usage", None)
        usage = None
        if usage_obj is not None:
            usage = CompletionUsage(
                prompt_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
            )

        return ChatCompletion(
            id=f"snowl-bridge-{id(response)}",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    message=ChatCompletionMessage(
                        content=str(content),
                        role="assistant",
                    ),
                )
            ],
            created=int(time.time()),
            model=model_name,
            object="chat.completion",
            usage=usage,
        )
    except ImportError:
        # OpenAI types not available; return a dict-like object
        return _DictChatCompletion(response, model_name)


class _DictChatCompletion:
    """Fallback ChatCompletion-like object when openai types aren't available."""

    def __init__(self, response: Any, model_name: str) -> None:
        message_obj = getattr(response, "message", None)
        self.content = ""
        if message_obj is not None:
            self.content = str(getattr(message_obj, "content", message_obj))
        self.model = model_name
        self.id = f"snowl-bridge-{id(response)}"
        self.object = "chat.completion"
        self.choices = [{"message": {"role": "assistant", "content": self.content}, "finish_reason": "stop"}]


def unpatch_openai() -> None:
    """Restore the original OpenAI SDK method."""
    global _original_openai_request, _patched_openai
    if not _patched_openai or _original_openai_request is None:
        return
    try:
        from openai._base_client import AsyncAPIClient
        AsyncAPIClient._request = _original_openai_request
    except ImportError:
        pass
    _original_openai_request = None
    _patched_openai = False
