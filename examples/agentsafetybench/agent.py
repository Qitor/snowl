"""Agent factory for AgentSafetyBench evaluation."""

from pathlib import Path

from snowl.agents import build_model_variants
from snowl.benchmarks.agentsafetybench import AgentSafetyBenchAgent
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, ProjectModelEntry, ProjectProviderConfig

PROJECT_DIR = Path(__file__).resolve().parent


def _build_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig):
    client = OpenAICompatibleChatClient(model_entry.config)
    return AgentSafetyBenchAgent(
        model_client=client,
        max_steps=10,
    )


@declare_agent(agent_id="agentsafetybench_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="agentsafetybench_agent",
        factory=_build_agent,
    )
