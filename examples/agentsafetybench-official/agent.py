from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.agents import build_model_variants
from snowl.benchmarks.agentsafetybench import (
    build_openai_agent_api,
    execute_agentsafetybench_case,
    persist_agentsafetybench_trajectory,
)
from snowl.core import AgentContext, AgentState, StopReason, agent as declare_agent
from snowl.model import OpenAICompatibleConfig, ProjectModelEntry, ProjectProviderConfig
from snowl.project_config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT = load_project_config(PROJECT_DIR)
ASB_SETTINGS = PROJECT.benchmark_settings("agentsafetybench")
DEFAULT_TEMPERATURE = 0.6
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_ROUNDS = 10


@dataclass
class AgentSafetyBenchOfficialAgent:
    model_config: OpenAICompatibleConfig
    agent_id: str = "agentsafetybench_official_agent"
    temperature: float = float(ASB_SETTINGS.get("temperature", DEFAULT_TEMPERATURE))
    max_tokens: int = int(ASB_SETTINGS.get("max_tokens", DEFAULT_MAX_TOKENS))
    max_rounds: int = int(ASB_SETTINGS.get("max_rounds", DEFAULT_MAX_ROUNDS))
    allow_empty: bool = bool(ASB_SETTINGS.get("allow_empty", False))
    _agent_api: Any = field(default=None, init=False, repr=False)

    def _ensure_agent_api(self) -> Any:
        if self._agent_api is None:
            self._agent_api = build_openai_agent_api(
                model_name=self.model_config.model,
                api_key=self.model_config.api_key,
                base_url=self.model_config.base_url,
                generation_config={
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
            )
        return self._agent_api

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        _ = tools
        sample = dict(context.metadata.get("sample", {}))
        sample_meta = dict(sample.get("metadata", {}))
        case = dict(sample_meta.get("case") or {})
        case.setdefault("id", sample_meta.get("case_id"))
        agent_api = self._ensure_agent_api()
        record = await asyncio.to_thread(
            execute_agentsafetybench_case,
            case,
            agent_api=agent_api,
            max_rounds=self.max_rounds,
            allow_empty=self.allow_empty,
        )
        saved_paths = await asyncio.to_thread(
            persist_agentsafetybench_trajectory,
            project_dir=PROJECT_DIR,
            sample_id=context.sample_id,
            case_id=case.get("id"),
            record=record,
            output_dir=ASB_SETTINGS.get("output_dir"),
            run_stamp=str(ASB_SETTINGS.get("run_stamp") or ""),
        )
        final_messages = list(record.get("output") or [])
        final_content = ""
        for message in reversed(final_messages):
            if str(message.get("role")) == "assistant" and str(message.get("content") or "").strip():
                final_content = str(message.get("content") or "").strip()
                break
        state.messages.append({"role": "assistant", "content": final_content})
        state.output = {
            "message": {"role": "assistant", "content": final_content},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "trace_events": [
                {
                    "event": "agentsafetybench.execution",
                    "case_id": case.get("id"),
                    "record": record,
                    "saved_paths": saved_paths,
                }
            ],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


def _build_agentsafetybench_agent(
    model_entry: ProjectModelEntry,
    provider: ProjectProviderConfig,
) -> AgentSafetyBenchOfficialAgent:
    _ = provider
    return AgentSafetyBenchOfficialAgent(model_config=model_entry.config)


@declare_agent(agent_id="agentsafetybench_official_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="agentsafetybench_official_agent",
        factory=_build_agentsafetybench_agent,
    )
