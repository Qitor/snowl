from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from snowl.errors import SnowlValidationError
from snowl.model import (
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    load_openai_compatible_config,
)


def test_load_config_env_only() -> None:
    cfg = load_openai_compatible_config(
        env={
            "OPENAI_API_KEY": "k",
            "OPENAI_MODEL": "gpt-test",
            "OPENAI_BASE_URL": "https://example.com/v1",
            "OPENAI_TIMEOUT": "12",
            "OPENAI_MAX_RETRIES": "4",
        }
    )
    assert cfg.api_key == "k"
    assert cfg.model == "gpt-test"
    assert cfg.base_url == "https://example.com/v1"
    assert cfg.timeout == 12.0
    assert cfg.max_retries == 4


def test_load_config_cli_overrides_env() -> None:
    cfg = load_openai_compatible_config(
        cli_overrides={"model": "override-model", "timeout": 5},
        env={"OPENAI_API_KEY": "k", "OPENAI_MODEL": "env-model"},
    )
    assert cfg.model == "override-model"
    assert cfg.timeout == 5.0


def test_load_config_missing_api_key_raises() -> None:
    with pytest.raises(SnowlValidationError, match="API key"):
        load_openai_compatible_config(env={"OPENAI_MODEL": "gpt-test"})


def test_load_config_missing_model_raises() -> None:
    with pytest.raises(SnowlValidationError, match="Missing model"):
        load_openai_compatible_config(env={"OPENAI_API_KEY": "k"})


def test_openai_client_generate_normalizes_usage_and_timing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-test"
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "hello world"}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    client = OpenAICompatibleChatClient(
        OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            api_key="k",
            model="gpt-test",
            timeout=3,
            max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )

    async def _run() -> None:
        response = await client.generate([{"role": "user", "content": "hi"}])
        assert response.message["content"] == "hello world"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5
        assert response.usage.total_tokens == 15
        assert response.timing.duration_ms >= 0
        await client.aclose()

    asyncio.run(_run())
