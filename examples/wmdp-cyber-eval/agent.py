"""WMDP-Cyber agent: asks the model a multiple-choice question and extracts the answer."""

from pathlib import Path

from snowl.agents import build_model_variants
from snowl.agents.chat_agent import ChatAgent
from snowl.core import agent
from snowl.model import OpenAICompatibleChatClient


def build_agent_for_model(model_entry, provider_config):
    """Build a ChatAgent for a given model entry."""
    return ChatAgent(
        agent_id="wmdp-cyber-agent",
        model_client=OpenAICompatibleChatClient(model_entry.config),
    )


@agent(agent_id="wmdp-cyber-agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="wmdp-cyber-agent",
        factory=build_agent_for_model,
    )
