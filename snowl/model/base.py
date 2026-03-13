"""Minimal provider-agnostic chat model client protocol used by agents and scorers.

Framework role:
- Defines the async `generate(messages, **kwargs)` contract so callers can swap provider implementations cleanly.

Runtime/usage wiring:
- Implemented by `OpenAICompatibleChatClient` and consumed by built-in agents/model-judge scorer.

Change guardrails:
- Keep protocol surface narrow and stable to avoid coupling agents/scorers to provider-specific APIs.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class ChatModelClient(Protocol):
    async def generate(
        self,
        messages: list[Mapping[str, Any]],
        **generation_kwargs: Any,
    ) -> Any: ...
