"""Model client protocols for provider-agnostic integration."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class ChatModelClient(Protocol):
    async def generate(
        self,
        messages: list[Mapping[str, Any]],
        **generation_kwargs: Any,
    ) -> Any: ...
