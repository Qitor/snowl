from __future__ import annotations

from pathlib import Path

from snowl.agents import ChatAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import ProjectModelEntry, ProjectProviderConfig, OpenAICompatibleChatClient


def _build_chat_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig) -> ChatAgent:
    _ = provider
    client = OpenAICompatibleChatClient(model_entry.config)
    return ChatAgent(
        model_client=client,
        agent_id="chatagent",
        default_generation_kwargs={"model": model_entry.model},
    )


@declare_agent(agent_id="chatagent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="chatagent",
        factory=_build_chat_agent,
    )
