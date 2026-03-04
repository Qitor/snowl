from __future__ import annotations

import pytest

from snowl.core import AgentContext, AgentState, validate_agent
from snowl.errors import SnowlValidationError


class GoodAgent:
    agent_id = "chat-agent"

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        return state


class MissingIdAgent:
    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        return state


class MissingRunAgent:
    agent_id = "bad-agent"


def test_validate_agent_ok() -> None:
    validate_agent(GoodAgent())


def test_validate_agent_missing_id() -> None:
    with pytest.raises(SnowlValidationError, match="agent_id"):
        validate_agent(MissingIdAgent())


def test_validate_agent_missing_run() -> None:
    with pytest.raises(SnowlValidationError, match="run"):
        validate_agent(MissingRunAgent())
