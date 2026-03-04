from __future__ import annotations

import os
import re

from snowl.agents import ChatAgent
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig


def _parse_models() -> list[str]:
    raw = os.getenv("SNOWL_AGENT_MODELS", "").strip()
    if raw:
        models = [x.strip() for x in raw.split(",") if x.strip()]
        if models:
            return models
    fallback = os.getenv("OPENAI_MODEL", "").strip()
    return [fallback] if fallback else ["gpt-4o-mini", "qwen2.5-72b-instruct"]


def _slug(text: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return out or "model"


def _build_agent(model_name: str, index: int) -> ChatAgent:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    api_key = os.getenv("OPENAI_API_KEY", "DUMMY_API_KEY_FOR_IMPORT").strip()
    timeout = float(os.getenv("OPENAI_TIMEOUT", "30"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    cfg = OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model_name,
        timeout=timeout,
        max_retries=max_retries,
    )
    client = OpenAICompatibleChatClient(cfg)
    return ChatAgent(
        model_client=client,
        agent_id=f"chatagent_{index}_{_slug(model_name)}",
        default_generation_kwargs={"model": model_name},
    )


@declare_agent()
def agents() -> list[ChatAgent]:
    return [_build_agent(model, i) for i, model in enumerate(_parse_models(), start=1)]
