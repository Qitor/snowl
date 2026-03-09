from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from snowl.benchmarks.agentsafetybench import (
    build_openai_agent_api,
    execute_agentsafetybench_case,
    persist_agentsafetybench_trajectory,
)
from snowl.core import AgentContext, AgentState, StopReason, agent as declare_agent
from snowl.utils.env import env_bool, env_float, env_int, env_str


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_NAME = "gpt-3.5-turbo"
DEFAULT_API_KEY = ""
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TEMPERATURE = 0.6
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_ROUNDS = 10


@dataclass
class AgentSafetyBenchOfficialAgent:
    agent_id: str = "agentsafetybench_official_agent"
    model_name: str = field(default_factory=lambda: env_str("SNOWL_AGENTSAFETYBENCH_MODEL", DEFAULT_MODEL_NAME))
    api_key: str | None = field(default_factory=lambda: (env_str("SNOWL_AGENTSAFETYBENCH_API_KEY") or DEFAULT_API_KEY))
    base_url: str | None = field(default_factory=lambda: (env_str("SNOWL_AGENTSAFETYBENCH_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL))
    temperature: float = field(default_factory=lambda: env_float("SNOWL_AGENTSAFETYBENCH_TEMPERATURE", DEFAULT_TEMPERATURE))
    max_tokens: int = field(default_factory=lambda: env_int("SNOWL_AGENTSAFETYBENCH_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    max_rounds: int = field(default_factory=lambda: env_int("SNOWL_AGENTSAFETYBENCH_MAX_ROUNDS", DEFAULT_MAX_ROUNDS))
    allow_empty: bool = field(default_factory=lambda: env_bool("SNOWL_AGENTSAFETYBENCH_ALLOW_EMPTY"))
    _agent_api: Any = field(default=None, init=False, repr=False)

    def _ensure_agent_api(self) -> Any:
        if self._agent_api is None:
            self._agent_api = build_openai_agent_api(
                model_name=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
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


@declare_agent()
def agent() -> AgentSafetyBenchOfficialAgent:
    return AgentSafetyBenchOfficialAgent()
