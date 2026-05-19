"""ToolEmu emulation orchestrator and toolkit utilities.

Framework role:
- ToolEmuEmulator wires EmulatedToolWrapper + ReActAgent + stub tools into a
  complete agent-emulator loop for one ToolEmu case.
- ToolEmuEmulationAgent satisfies the Agent protocol so it can be used in
  project.yml agent.py with the standard eval pipeline.
- Toolkit loading and stub tool generation convert all_toolkits.json schemas
  into Snowl ToolSpec objects.

Runtime/usage wiring:
- Used by eval runtime when ToolEmu samples have emulation_mode=True in metadata.
- Key top-level symbols: ToolEmuEmulator, ToolEmuEmulationAgent, load_toolkit_data.

Change guardrails:
- Emulator.run() determines the trajectory structure consumed by ToolEmuScorer;
  trajectory format changes are scorer-breaking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.agents.react_agent import ReActAgent
from snowl.benchmarks.utils import default_reference_path
from snowl.core.agent import AgentContext, AgentState
from snowl.core.tool import ToolSpec
from snowl.model.openai_compatible import OpenAICompatibleChatClient
from snowl.tools.emulated_tool import (
    EmulationScratchpad,
    EmulatedToolWrapper,
    make_stub_tool,
    render_toolkit_description,
)


def load_toolkit_data(path: str | None = None) -> dict[str, dict[str, Any]]:
    """Load all_toolkits.json and return mapping from toolkit name to toolkit dict."""
    if path is None:
        path = default_reference_path(
            __file__,
            "ToolEmu",
            "assets",
            "all_toolkits.json",
        )
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"ToolEmu toolkit data not found: {path}")
    with open(p) as f:
        toolkits = json.load(f)
    result: dict[str, dict[str, Any]] = {}
    for toolkit in toolkits:
        name = toolkit.get("toolkit") or toolkit.get("name_for_model", "")
        if name:
            result[name] = toolkit
    return result


class ToolEmuEmulator:
    """High-level emulator that wraps ReActAgent with EmulatedToolWrapper."""

    def __init__(
        self,
        *,
        agent_llm: OpenAICompatibleChatClient,
        emulator_llm: OpenAICompatibleChatClient,
        critiquer_llm: OpenAICompatibleChatClient | None = None,
        simulator_type: str = "std_thought",
        scheduler: Any | None = None,
        max_steps: int = 10,
        num_critique_steps: int = 0,
        toolkit_data: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.agent_llm = agent_llm
        self.emulator_llm = emulator_llm
        self.critiquer_llm = critiquer_llm
        self.simulator_type = simulator_type
        self.scheduler = scheduler
        self.max_steps = max_steps
        self.num_critique_steps = num_critique_steps
        self.toolkit_data = toolkit_data or {}

    async def run(
        self,
        sample: dict[str, Any],
        context: AgentContext,
    ) -> AgentState:
        """Run the agent-emulator loop for one ToolEmu case.

        1. Extract toolkits, user_input, etc. from sample metadata
        2. Load toolkit schemas, build toolkit description string
        3. Create stub ToolSpecs for each tool
        4. Create EmulatedToolWrapper with adversarial context
        5. Create ReActAgent with the wrapper as middleware
        6. Run agent.run(state, context, tools=stub_tools)
        7. Embed trajectory in state.output trace_events
        8. Return state
        """
        metadata = sample.get("metadata") or {}
        toolkit_names = list(metadata.get("toolkits") or [])
        user_input = str(sample.get("input") or "")
        underspecifications = metadata.get("underspecifications")
        risky_outcomes = metadata.get("potential_risky_outcomes")
        risky_actions = metadata.get("potential_risky_actions")

        # Load toolkit schemas
        toolkit_schemas = self._load_toolkit_schemas(toolkit_names)
        toolkit_descriptions = self._build_toolkit_description(toolkit_schemas)

        # Build tool schemas dict for the wrapper (name -> tool spec dict)
        tool_schemas: dict[str, dict[str, Any]] = {}
        for _tk_name, tk in toolkit_schemas.items():
            for tool in tk.get("tools", []):
                tool_schemas[tool.get("name", "")] = tool

        # Create stub tools
        stub_tools = self._build_stub_tools(toolkit_schemas)

        # Build the wrapper
        emit_fn = context.metadata.get("__snowl_emit_event")
        wrapper = EmulatedToolWrapper(
            emulator_client=self.emulator_llm,
            critiquer_client=self.critiquer_llm,
            simulator_type=self.simulator_type,
            scheduler=self.scheduler,
            tool_schemas=tool_schemas,
            num_critique_steps=self.num_critique_steps,
            emit_fn=emit_fn,
            underspecifications=underspecifications,
            risky_outcome=", ".join(risky_outcomes) if risky_outcomes else None,
            risky_actions=risky_actions,
            user_input=user_input,
            toolkit_descriptions=toolkit_descriptions,
        )

        # Create ReActAgent with the wrapper
        agent = ReActAgent(
            model_client=self.agent_llm,
            max_steps=self.max_steps,
            temperature=0.0,
            middlewares=[wrapper],
        )

        # Build initial state
        state = AgentState(
            messages=[{"role": "user", "content": user_input}],
            actions=[],
            observations=[],
            stop_reason=None,
            output=None,
        )

        # Run the agent
        result_state = await agent.run(state, context, tools=stub_tools)

        # Embed trajectory in trace_events
        trajectory = self._build_trajectory(result_state, wrapper.scratchpad)
        trace_events = list((result_state.output or {}).get("trace_events", []))
        trace_events.append(
            {
                "event": "toolemu.emulation",
                "trajectory": trajectory,
                "simulator_type": self.simulator_type,
            }
        )
        if result_state.output is not None:
            result_state.output["trace_events"] = trace_events

        return result_state

    def _load_toolkit_schemas(self, toolkit_names: list[str]) -> dict[str, dict[str, Any]]:
        """Load toolkit dicts from toolkit_data by name."""
        schemas: dict[str, dict[str, Any]] = {}
        for name in toolkit_names:
            if name in self.toolkit_data:
                schemas[name] = self.toolkit_data[name]
        return schemas

    def _build_stub_tools(self, toolkit_schemas: dict[str, dict[str, Any]]) -> list[ToolSpec]:
        """Create stub ToolSpec for each tool across all toolkits."""
        stubs: list[ToolSpec] = []
        for _tk_name, tk in toolkit_schemas.items():
            for tool in tk.get("tools", []):
                name = tool.get("name", "")
                summary = tool.get("summary", "")
                parameters = _tool_params_to_schema(tool.get("parameters", []))
                stubs.append(make_stub_tool(name, summary, parameters))
        return stubs

    def _build_toolkit_description(self, toolkit_schemas: dict[str, dict[str, Any]]) -> str:
        """Build the combined toolkit description string for the emulator prompt."""
        parts: list[str] = []
        for _name, tk in toolkit_schemas.items():
            parts.append(render_toolkit_description(tk, detail_level="low"))
        return "\n\n".join(parts)

    def _build_trajectory(
        self,
        state: AgentState,
        scratchpad: EmulationScratchpad,
    ) -> dict[str, Any]:
        """Build the trajectory dict for the toolemu.emulation trace event."""
        actions = [
            {"action": a.payload.get("tool_name", ""), "action_input": a.payload.get("arguments", "")}
            for a in state.actions
            if a.action_type == "tool_call"
        ]
        observations = [
            {"tool_name": o.payload.get("tool_name", ""), "result": o.payload.get("result", "")}
            for o in state.observations
            if o.observation_type == "tool_result"
        ]
        return {
            "actions": actions,
            "observations": observations,
            "scratchpad": [dict(e) for e in scratchpad.entries],
        }


def _tool_params_to_schema(params: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert a ToolEmu tool parameters list to a JSON-schema-style parameters dict."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in params:
        p_name = param.get("name", "")
        p_type = param.get("type", "string").lower()
        p_desc = param.get("description", "")

        type_map = {
            "string": "string",
            "integer": "integer",
            "int": "integer",
            "number": "number",
            "float": "number",
            "boolean": "boolean",
            "bool": "boolean",
            "array": "array",
            "list": "array",
            "object": "object",
            "dict": "object",
        }
        json_type = type_map.get(p_type, "string")

        prop: dict[str, Any] = {"type": json_type}
        if p_desc:
            prop["description"] = p_desc
        properties[p_name] = prop

        if param.get("required"):
            required.append(p_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# ToolEmuEmulationAgent — Agent protocol wrapper for eval pipeline
# ---------------------------------------------------------------------------


class ToolEmuEmulationAgent:
    """Agent wrapper that delegates to ToolEmuEmulator for LM-emulated tool execution.

    Satisfies the snowl Agent protocol so it can be used in project.yml agent.py.
    Extracts sample metadata from AgentContext.metadata["sample"]["metadata"] which
    the eval pipeline populates from the adapter's _row_to_sample() output.
    """

    def __init__(
        self,
        *,
        agent_llm: OpenAICompatibleChatClient,
        emulator_llm: OpenAICompatibleChatClient,
        critiquer_llm: OpenAICompatibleChatClient | None = None,
        simulator_type: str = "std_thought",
        scheduler: Any | None = None,
        max_steps: int = 10,
        num_critique_steps: int = 0,
        toolkit_data: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.agent_id = "toolemu_emulation_agent"
        self._emulator = ToolEmuEmulator(
            agent_llm=agent_llm,
            emulator_llm=emulator_llm,
            critiquer_llm=critiquer_llm,
            simulator_type=simulator_type,
            scheduler=scheduler,
            max_steps=max_steps,
            num_critique_steps=num_critique_steps,
            toolkit_data=toolkit_data,
        )

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools=None,
    ) -> AgentState:
        """Run the agent-emulator loop, extracting sample metadata from context."""
        # Extract sample metadata from eval pipeline context
        sample = dict(context.metadata.get("sample", {}))
        sample_metadata = dict(sample.get("metadata", {}))

        # Build sample dict for ToolEmuEmulator
        user_input = str(sample.get("input") or "")
        if not user_input:
            # Fallback: extract from state messages
            for msg in state.messages:
                if msg.get("role") == "user" and msg.get("content"):
                    user_input = str(msg["content"])
                    break

        sample_dict = {
            "id": context.sample_id or sample.get("id", "unknown"),
            "input": user_input,
            "metadata": sample_metadata,
        }

        return await self._emulator.run(sample_dict, context)
