from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.agents import build_model_variants
from snowl.benchmarks.toolemu import build_tool_emu_llm, execute_tool_emu_case
from snowl.benchmarks.toolemu.runtime import persist_tool_emu_trajectory
from snowl.core import AgentContext, AgentState, StopReason, agent as declare_agent
from snowl.model import OpenAICompatibleConfig, ProjectModelEntry, ProjectProviderConfig
from snowl.project_config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT = load_project_config(PROJECT_DIR)
TOOLEMU_SETTINGS = PROJECT.benchmark_settings("toolemu")


def _build_case(sample: dict[str, Any], sample_meta: dict[str, Any]) -> dict[str, Any]:
    case = dict(sample_meta.get("case") or {})
    if case:
        return case
    return {
        "name": sample_meta.get("name") or sample.get("id") or "adhoc_case",
        "Toolkits": list(sample_meta.get("toolkits") or []),
        "User Instruction": sample.get("input") or "",
        "Underspecifications": dict(sample_meta.get("underspecifications") or {}),
        "Expected Achievements": list(sample_meta.get("expected_achievements") or []),
        "Potential Risky Outcomes": list(sample_meta.get("potential_risky_outcomes") or []),
        "Potential Risky Actions": list(sample_meta.get("potential_risky_actions") or []),
    }


@dataclass
class ToolEmuOfficialAgent:
    model_config: OpenAICompatibleConfig
    simulator_config: OpenAICompatibleConfig
    agent_id: str = "toolemu_official_agent"
    agent_type: str = str(TOOLEMU_SETTINGS.get("agent_type", "naive"))
    simulator_type: str = str(TOOLEMU_SETTINGS.get("simulator_type", "adv_thought"))
    max_iterations: int = int(TOOLEMU_SETTINGS.get("max_iterations", 15))
    verbose: bool = bool(TOOLEMU_SETTINGS.get("verbose", False))
    agent_max_tokens: int | None = (
        int(TOOLEMU_SETTINGS["agent_max_tokens"])
        if TOOLEMU_SETTINGS.get("agent_max_tokens") is not None
        else None
    )
    simulator_max_tokens: int | None = (
        int(TOOLEMU_SETTINGS["simulator_max_tokens"])
        if TOOLEMU_SETTINGS.get("simulator_max_tokens") is not None
        else None
    )
    _agent_llm: Any = field(default=None, init=False, repr=False)
    _simulator_llm: Any = field(default=None, init=False, repr=False)

    def _ensure_llms(self) -> tuple[Any, Any]:
        if self._agent_llm is None:
            self._agent_llm = build_tool_emu_llm(
                "agent",
                model_name=self.model_config.model,
                openai_api_key=self.model_config.api_key,
                openai_api_base=self.model_config.base_url,
                request_timeout=int(self.model_config.timeout),
                max_retries=self.model_config.max_retries,
                max_tokens=self.agent_max_tokens,
            )
        if self._simulator_llm is None:
            self._simulator_llm = build_tool_emu_llm(
                "simulator",
                model_name=self.simulator_config.model,
                openai_api_key=self.simulator_config.api_key,
                openai_api_base=self.simulator_config.base_url,
                request_timeout=int(self.simulator_config.timeout),
                max_retries=self.simulator_config.max_retries,
                max_tokens=self.simulator_max_tokens,
            )
        return self._agent_llm, self._simulator_llm

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        _ = tools
        sample_id = context.sample_id
        sample = dict(context.metadata.get("sample", {}))
        sample_meta = dict(sample.get("metadata", {}))
        case = _build_case(sample, sample_meta)
        agent_llm, simulator_llm = self._ensure_llms()
        trajectory, simple_trajectory = await asyncio.to_thread(
            execute_tool_emu_case,
            case,
            agent_llm=agent_llm,
            simulator_llm=simulator_llm,
            agent_type=self.agent_type,
            simulator_type=self.simulator_type,
            max_iterations=self.max_iterations,
            verbose=self.verbose,
        )
        if trajectory.get("error"):
            raise RuntimeError(f"ToolEmu execution error: {trajectory['error']}")

        saved_paths = await asyncio.to_thread(
            persist_tool_emu_trajectory,
            project_dir=PROJECT_DIR,
            sample_id=sample_id,
            case_name=str(case.get("name") or ""),
            trajectory=trajectory,
            simple_trajectory=simple_trajectory,
            output_dir=TOOLEMU_SETTINGS.get("output_dir"),
            run_stamp=str(TOOLEMU_SETTINGS.get("run_stamp") or ""),
            extra={
                "agent_type": self.agent_type,
                "simulator_type": self.simulator_type,
                "sample_id": sample_id,
                "variant_id": str(context.metadata.get("variant_id") or "default"),
                "agent_model": self.model_config.model,
                "simulator_model": self.simulator_config.model,
            },
        )

        content = str(trajectory.get("output") or "").strip() or simple_trajectory.strip()
        state.messages.append({"role": "assistant", "content": content})
        state.output = {
            "message": {"role": "assistant", "content": content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [
                {
                    "event": "toolemu.emulation",
                    "case_name": case.get("name"),
                    "toolkits": case.get("Toolkits") or [],
                    "agent_type": self.agent_type,
                    "simulator_type": self.simulator_type,
                    "trajectory": trajectory,
                    "simple_trajectory": simple_trajectory,
                    "saved_paths": saved_paths,
                }
            ],
            "artifacts": saved_paths,
        }
        state.stop_reason = StopReason.COMPLETED
        return state

def _build_toolemu_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> ToolEmuOfficialAgent:
    _ = provider
    if PROJECT.judge is None:
        raise RuntimeError("toolemu-official requires judge.model in project.yml for simulator/evaluator roles")
    return ToolEmuOfficialAgent(
        model_config=model_entry.config,
        simulator_config=PROJECT.judge.config,
    )


@declare_agent(agent_id="toolemu_official_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="toolemu_official_agent",
        factory=_build_toolemu_agent,
    )
