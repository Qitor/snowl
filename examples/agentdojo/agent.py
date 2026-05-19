"""Agent definition for AgentDojo eval.

Creates AgentDojoAgent instances that use ReActAgent with StatefulToolExecutor
middleware for stateful tool execution in banking/travel suites.
"""

from __future__ import annotations

from pathlib import Path

from snowl.agents import build_model_variants
from snowl.benchmarks.agentdojo.agent import AgentDojoAgent
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig, ProjectModelEntry, ProjectProviderConfig


PROJECT_DIR = Path(__file__).resolve().parent


def _build_agentdojo_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> AgentDojoAgent:
    """Build an AgentDojoAgent for the given model variant."""
    agent_client = OpenAICompatibleChatClient(model_entry.config)

    return AgentDojoAgent(
        model_client=agent_client,
        max_steps=15,
    )


@declare_agent(agent_id="agentdojo_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="agentdojo_agent",
        factory=_build_agentdojo_agent,
    )
