from __future__ import annotations

import os
from pathlib import Path

from snowl.agents import ChatAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import (
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    ProjectModelEntry,
    ProjectProviderConfig,
)


def _api_key() -> str:
    key = os.getenv("SNOWL_SMOKE_API_KEY", "").strip() or os.getenv("INF_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set SNOWL_SMOKE_API_KEY or INF_API_KEY before running this example.")
    return key


def _build_chat_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> ChatAgent:
    _ = provider
    metadata = model_entry.metadata or {}
    base_url = metadata.get("base_url") or model_entry.config.base_url
    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            provider_id="remote-smoke",
            base_url=base_url,
            api_key=_api_key(),
            model=model_entry.model,
            timeout=120,
            max_retries=1,
        )
    )
    return ChatAgent(
        model_client=client,
        agent_id="chatagent",
        default_generation_kwargs={
            "model": model_entry.model,
            "max_tokens": int(os.getenv("SNOWL_SMOKE_MAX_TOKENS", "256")),
            "temperature": float(os.getenv("SNOWL_SMOKE_TEMPERATURE", "0")),
        },
    )


@declare_agent(agent_id="chatagent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="chatagent",
        factory=_build_chat_agent,
    )
