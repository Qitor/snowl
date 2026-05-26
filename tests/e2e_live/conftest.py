"""Shared fixtures for live E2E tests that call real LLM APIs.

Usage::

    SNOWL_LIVE_API_KEY=sk-... \\
    SNOWL_LIVE_BASE_URL=https://api.openai.com/v1 \\
    SNOWL_LIVE_MODEL=gpt-4o-mini \\
    pytest -m live tests/e2e_live/ -v --timeout=120
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from snowl.model.openai_compatible import OpenAICompatibleChatClient, OpenAICompatibleConfig


# ---------------------------------------------------------------------------
# Configuration fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def live_config() -> OpenAICompatibleConfig:
    """Build OpenAICompatibleConfig from env vars, skip if missing."""
    api_key = os.environ.get("SNOWL_LIVE_API_KEY", "").strip()
    base_url = os.environ.get("SNOWL_LIVE_BASE_URL", "").strip()
    model = os.environ.get("SNOWL_LIVE_MODEL", "").strip()
    if not all([api_key, base_url, model]):
        pytest.skip(
            "Set SNOWL_LIVE_API_KEY, SNOWL_LIVE_BASE_URL, SNOWL_LIVE_MODEL "
            "to run live E2E tests"
        )
    return OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=60.0,
        max_retries=2,
        provider_id="live_test",
    )


# ---------------------------------------------------------------------------
# Model client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def live_client(live_config: OpenAICompatibleConfig) -> OpenAICompatibleChatClient:
    """Async model client with auto-close on teardown."""
    client = OpenAICompatibleChatClient(live_config)
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# Cost tracker
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def cost_tracker() -> dict:
    """Session-scoped token usage tracker. Prints summary at session end."""
    tracker: dict = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "test_count": 0,
    }
    yield tracker
    # Rough gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output
    est = (tracker["input_tokens"] * 0.15 + tracker["output_tokens"] * 0.60) / 1_000_000
    print(
        f"\nLive test session: {tracker['test_count']} tests, "
        f"{tracker['total_tokens']} tokens, ~${est:.4f} estimated cost"
    )


def track_usage(tracker: dict, usage: dict | object) -> None:
    """Extract usage from an outcome and accumulate in the tracker."""
    if usage is None:
        return
    if hasattr(usage, "input_tokens"):
        tracker["input_tokens"] += int(getattr(usage, "input_tokens", 0))
        tracker["output_tokens"] += int(getattr(usage, "output_tokens", 0))
        tracker["total_tokens"] += int(getattr(usage, "total_tokens", 0))
    elif isinstance(usage, dict):
        tracker["input_tokens"] += int(usage.get("input_tokens", 0))
        tracker["output_tokens"] += int(usage.get("output_tokens", 0))
        tracker["total_tokens"] += int(usage.get("total_tokens", 0))
    tracker["test_count"] += 1


# ---------------------------------------------------------------------------
# Project scaffolding helper
# ---------------------------------------------------------------------------

def write_live_project(
    base_dir,
    config: OpenAICompatibleConfig,
    *,
    task_id: str = "e2e-cli",
    sample_input: str = "Say hello.",
    sample_target: str = "hello",
) -> None:
    """Write project.yml + task.py + agent.py + scorer.py for CLI E2E tests."""
    base_dir = base_dir if hasattr(base_dir, "mkdir") else __import__("pathlib").Path(base_dir)

    (base_dir / "project.yml").write_text(f"""\
project:
  name: e2e-live-test
  root_dir: .

provider:
  id: live
  kind: openai_compatible
  base_url: {config.base_url}
  api_key: {config.api_key}
  timeout: 60
  max_retries: 2

agent_matrix:
  models:
    - id: default
      model: {config.model}

eval:
  benchmark: e2e-live
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
  split: test
  limit: 1

runtime:
  max_running_trials: 1
  max_container_slots: 0
""")

    (base_dir / "task.py").write_text(f"""\
from snowl.core.task import Task
from snowl.core.env import EnvSpec

task = Task(
    task_id="{task_id}",
    env_spec=EnvSpec(env_type="local"),
    sample_iter_factory=lambda: iter([{{"id": "s1", "input": "{sample_input}", "target": "{sample_target}"}}]),
)
""")

    (base_dir / "agent.py").write_text(f"""\
import os
from snowl.agents.chat_agent import ChatAgent
from snowl.model.openai_compatible import OpenAICompatibleChatClient, OpenAICompatibleConfig

_config = OpenAICompatibleConfig(
    base_url=os.environ.get("SNOWL_LIVE_BASE_URL", "{config.base_url}"),
    api_key=os.environ.get("SNOWL_LIVE_API_KEY", "{config.api_key}"),
    model=os.environ.get("SNOWL_LIVE_MODEL", "{config.model}"),
    timeout=60.0,
    max_retries=2,
)
agent = ChatAgent(OpenAICompatibleChatClient(_config), default_generation_kwargs={{"max_tokens": 256}})
""")

    (base_dir / "scorer.py").write_text("""\
from snowl.scorer import includes

scorer = includes()
""")
