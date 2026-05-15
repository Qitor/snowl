"""Agent definition for ToolEmu emulation eval.

Creates ToolEmuEmulationAgent instances that use an LM emulator to generate
realistic tool observations instead of executing real tools.
"""

from __future__ import annotations

import os
from pathlib import Path

from snowl.agents import build_model_variants
from snowl.benchmarks.toolemu.emulation import ToolEmuEmulationAgent, load_toolkit_data
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig, ProjectModelEntry, ProjectProviderConfig


PROJECT_DIR = Path(__file__).resolve().parent
TOOLKIT_DATA = load_toolkit_data()

SIMULATOR_TYPE = os.environ.get("TOOLEMU_SIMULATOR_TYPE", "std_thought")


def _build_emulation_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> ToolEmuEmulationAgent:
    """Build a ToolEmuEmulationAgent for the given model variant."""
    agent_client = OpenAICompatibleChatClient(model_entry.config)

    # Emulator uses the same model + provider
    emulator_config = OpenAICompatibleConfig(
        base_url=model_entry.config.base_url,
        api_key=model_entry.config.api_key,
        model=model_entry.model,
        timeout=model_entry.config.timeout,
        max_retries=model_entry.config.max_retries,
        provider_id=model_entry.config.provider_id,
    )
    emulator_client = OpenAICompatibleChatClient(emulator_config)

    return ToolEmuEmulationAgent(
        agent_llm=agent_client,
        emulator_llm=emulator_client,
        simulator_type=SIMULATOR_TYPE,
        toolkit_data=TOOLKIT_DATA,
        max_steps=10,
    )


@declare_agent(agent_id="toolemu_emulation_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="toolemu_emulation_agent",
        factory=_build_emulation_agent,
    )
