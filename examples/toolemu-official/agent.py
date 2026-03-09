from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.benchmarks.toolemu import build_tool_emu_llm, execute_tool_emu_case
from snowl.benchmarks.toolemu.runtime import persist_tool_emu_trajectory
from snowl.core import AgentContext, AgentState, StopReason, agent as declare_agent
from snowl.utils.env import env_bool, env_int, env_optional_int, env_str


PROJECT_DIR = Path(__file__).resolve().parent


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
    agent_id: str = "toolemu_official_agent"
    agent_type: str = field(default_factory=lambda: env_str("SNOWL_TOOLEMU_AGENT_TYPE", "naive") or "naive")
    simulator_type: str = field(default_factory=lambda: env_str("SNOWL_TOOLEMU_SIMULATOR_TYPE", "adv_thought") or "adv_thought")
    max_iterations: int = field(default_factory=lambda: env_int("SNOWL_TOOLEMU_MAX_ITERATIONS", 15))
    verbose: bool = field(default_factory=lambda: env_bool("SNOWL_TOOLEMU_VERBOSE"))
    agent_model_name: str = field(default_factory=lambda: env_str("SNOWL_TOOLEMU_AGENT_MODEL", "Qwen/Qwen3-8B"))
    agent_api_key: str | None = field(default_factory=lambda: (env_str("SNOWL_TOOLEMU_AGENT_API_KEY") or ""))
    agent_base_url: str | None = field(default_factory=lambda: (env_str("SNOWL_TOOLEMU_AGENT_BASE_URL", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"))
    agent_max_tokens: int | None = field(default_factory=lambda: env_optional_int("SNOWL_TOOLEMU_AGENT_MAX_TOKENS"))
    simulator_model_name: str = field(default_factory=lambda: env_str("SNOWL_TOOLEMU_SIMULATOR_MODEL", "Qwen/Qwen3-8B"))
    simulator_api_key: str | None = field(default_factory=lambda: (env_str("SNOWL_TOOLEMU_SIMULATOR_API_KEY") or ""))
    simulator_base_url: str | None = field(default_factory=lambda: (env_str("SNOWL_TOOLEMU_SIMULATOR_BASE_URL", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"))
    simulator_max_tokens: int | None = field(default_factory=lambda: env_optional_int("SNOWL_TOOLEMU_SIMULATOR_MAX_TOKENS"))
    _agent_llm: Any = field(default=None, init=False, repr=False)
    _simulator_llm: Any = field(default=None, init=False, repr=False)

    def _ensure_llms(self) -> tuple[Any, Any]:
        if self._agent_llm is None:
            self._agent_llm = build_tool_emu_llm(
                "agent",
                model_name=self.agent_model_name,
                openai_api_key=self.agent_api_key,
                openai_api_base=self.agent_base_url,
                max_tokens=self.agent_max_tokens,
            )
        if self._simulator_llm is None:
            self._simulator_llm = build_tool_emu_llm(
                "simulator",
                model_name=self.simulator_model_name,
                openai_api_key=self.simulator_api_key,
                openai_api_base=self.simulator_base_url,
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
            extra={
                "agent_type": self.agent_type,
                "simulator_type": self.simulator_type,
                "sample_id": sample_id,
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


@declare_agent()
def agent() -> ToolEmuOfficialAgent:
    return ToolEmuOfficialAgent()
