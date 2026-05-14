"""Agent factory for the agent-safety-sweep example.

Builds a ChatAgent per model variant using per-model provider overrides
from project.yml. Models that require `enable_thinking: false` (GLM-5.1,
Qwen3.5) get it via the `disable_thinking` metadata flag.
"""

from __future__ import annotations

from pathlib import Path

from snowl.agents import ChatAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import (
    OpenAICompatibleChatClient,
    ProjectModelEntry,
    ProjectProviderConfig,
)


def _build_chat_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> ChatAgent:
    _ = provider
    config = model_entry.config
    metadata = model_entry.metadata or {}

    generation_kwargs: dict = {
        "model": model_entry.model,
        "max_tokens": 4096,
        "temperature": 0.0,
    }

    # GLM-5.1 and Qwen3.5 require disable_thinking
    if metadata.get("disable_thinking"):
        generation_kwargs["chat_template_kwargs"] = {"enable_thinking": False}

    client = OpenAICompatibleChatClient(config)

    return ChatAgent(
        model_client=client,
        agent_id="chatagent",
        default_generation_kwargs=generation_kwargs,
    )


@declare_agent(agent_id="chatagent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="chatagent",
        factory=_build_chat_agent,
    )
