"""Core protocol definitions shared across Snowl subsystems.

Framework role:
- Defines provider-agnostic protocols (e.g., ChatModelClient) that decouple
  core contracts from concrete implementations.

Runtime/usage wiring:
- Implemented by ``OpenAICompatibleChatClient`` in ``snowl.model``.
- Consumed by agents, scorers, and tools that need a model client but
  should not depend on a specific provider.

Change guardrails:
- Keep protocol surfaces narrow and stable to avoid coupling agents/scorers
  to provider-specific APIs.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class ChatModelClient(Protocol):
    async def generate(
        self,
        messages: list[Mapping[str, Any]],
        **generation_kwargs: Any,
    ) -> Any: ...
