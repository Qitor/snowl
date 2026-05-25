"""Tests for Adapter SDK: BaseFrameworkAdapter, AdapterRegistry, concrete adapters, and discovery integration."""

import asyncio
import pytest

from snowl.adapters.base import BaseFrameworkAdapter
from snowl.adapters.registry import AdapterRegistry, get_default_adapter_registry
from snowl.adapters.custom import CustomAdapter
from snowl.adapters.langgraph import LangGraphAdapter, _LangGraphAgent
from snowl.adapters.openai_agents import OpenAIAgentsAdapter, _OpenAIAgentsAgent
from snowl.core.agent import AgentState, StopReason
from snowl.errors import SnowlValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_state() -> AgentState:
    return AgentState(messages=[], actions=[], observations=[], output=None, stop_reason=None)


# ---------------------------------------------------------------------------
# BaseFrameworkAdapter
# ---------------------------------------------------------------------------

class TestBaseFrameworkAdapter:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseFrameworkAdapter()

    def test_subclass_must_implement_framework_name_and_wrap(self):
        class IncompleteAdapter(BaseFrameworkAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_minimal_subclass(self):
        class MinimalAdapter(BaseFrameworkAdapter):
            @property
            def framework_name(self) -> str:
                return "minimal"

            def wrap(self, agent, **kwargs):
                return agent

        adapter = MinimalAdapter()
        assert adapter.framework_name == "minimal"
        # Default methods
        assert adapter.unwrap_state(_fresh_state()) is not None
        assert adapter.wrap_result(None, _fresh_state()) is not None
        assert adapter.wrap_tools(None) is None


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_register_and_get(self):
        class TestAdapter(BaseFrameworkAdapter):
            @property
            def framework_name(self) -> str:
                return "test"

            def wrap(self, agent, **kwargs):
                return agent

        registry = AdapterRegistry()
        registry.register("test", TestAdapter)
        adapter = registry.get("test")
        assert isinstance(adapter, TestAdapter)

    def test_get_unknown_raises(self):
        registry = AdapterRegistry()
        with pytest.raises(SnowlValidationError, match="No adapter registered"):
            registry.get("unknown")

    def test_list_frameworks(self):
        class A(BaseFrameworkAdapter):
            @property
            def framework_name(self): return "z_adapter"
            def wrap(self, agent, **kwargs): return agent

        class B(BaseFrameworkAdapter):
            @property
            def framework_name(self): return "a_adapter"
            def wrap(self, agent, **kwargs): return agent

        registry = AdapterRegistry()
        registry.register("z_adapter", A)
        registry.register("a_adapter", B)
        assert registry.list_frameworks() == ["a_adapter", "z_adapter"]

    def test_register_rejects_empty_name(self):
        registry = AdapterRegistry()
        with pytest.raises(SnowlValidationError, match="non-empty string"):
            registry.register("", object)

    def test_register_rejects_non_adapter(self):
        registry = AdapterRegistry()
        with pytest.raises(SnowlValidationError, match="BaseFrameworkAdapter subclass"):
            registry.register("bad", object)

    def test_has(self):
        registry = AdapterRegistry()
        assert not registry.has("missing")


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    def test_has_builtin_adapters(self):
        registry = get_default_adapter_registry()
        assert registry.has("custom")
        assert registry.has("langgraph")
        assert registry.has("openai_agents")

    def test_list_includes_builtins(self):
        registry = get_default_adapter_registry()
        frameworks = registry.list_frameworks()
        assert "custom" in frameworks
        assert "langgraph" in frameworks
        assert "openai_agents" in frameworks


# ---------------------------------------------------------------------------
# CustomAdapter
# ---------------------------------------------------------------------------

class TestCustomAdapter:
    @pytest.mark.asyncio
    async def test_wrap_async_function(self):
        async def my_agent(messages, tools):
            return "Hello from custom"

        adapter = CustomAdapter()
        agent = adapter.wrap(my_agent)
        assert agent.agent_id == "custom"

        state = _fresh_state()
        result = await agent.run(state, None, None)
        assert result.stop_reason == StopReason.COMPLETED
        assert "Hello from custom" in result.messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_wrap_with_custom_id(self):
        async def my_agent(messages, tools):
            return "result"

        adapter = CustomAdapter()
        agent = adapter.wrap(my_agent, agent_id="my_custom")
        assert agent.agent_id == "my_custom"

    def test_wrap_rejects_non_callable(self):
        adapter = CustomAdapter()
        with pytest.raises(TypeError, match="callable"):
            adapter.wrap(42)

    @pytest.mark.asyncio
    async def test_wrap_agent_returning_agent_state(self):
        async def my_agent(messages, tools):
            state = _fresh_state()
            state.stop_reason = StopReason.COMPLETED
            state.output = {"message": {"role": "assistant", "content": "direct"}}
            return state

        adapter = CustomAdapter()
        agent = adapter.wrap(my_agent)
        result = await agent.run(_fresh_state(), None, None)
        assert result.output["message"]["content"] == "direct"


# ---------------------------------------------------------------------------
# LangGraphAdapter
# ---------------------------------------------------------------------------

class TestLangGraphAdapter:
    @pytest.mark.asyncio
    async def test_wrap_none_graph(self):
        adapter = LangGraphAdapter()
        agent = adapter.wrap(None)
        state = _fresh_state()
        from snowl.core.agent import AgentContext
        context = AgentContext(task_id="t1", sample_id=None, metadata={})
        result = await agent.run(state, context, None)
        assert result.stop_reason == StopReason.COMPLETED
        # The "not configured" message is in output, not necessarily in messages
        assert "not configured" in result.output["message"]["content"]

    @pytest.mark.asyncio
    async def test_wrap_graph_with_ainvoke(self):
        class MockGraph:
            async def ainvoke(self, input_data):
                return {"output": "graph result", "messages": []}

        adapter = LangGraphAdapter()
        agent = adapter.wrap(MockGraph())
        state = _fresh_state()
        from snowl.core.agent import AgentContext
        context = AgentContext(task_id="t1", sample_id=None, metadata={})
        result = await agent.run(state, context, None)
        assert result.stop_reason == StopReason.COMPLETED
        assert "graph result" in result.messages[-1]["content"]

    def test_wrap_rejects_non_graph(self):
        adapter = LangGraphAdapter()
        with pytest.raises(TypeError, match="ainvoke"):
            adapter.wrap("not a graph")


# ---------------------------------------------------------------------------
# OpenAIAgentsAdapter
# ---------------------------------------------------------------------------

class TestOpenAIAgentsAdapter:
    @pytest.mark.asyncio
    async def test_wrap_none_client(self):
        adapter = OpenAIAgentsAdapter()
        agent = adapter.wrap(None)
        state = _fresh_state()
        result = await agent.run(state, None, None)
        assert result.stop_reason == StopReason.COMPLETED
        assert "not configured" in result.output["message"]["content"]

    @pytest.mark.asyncio
    async def test_wrap_client_with_responses(self):
        class MockResponse:
            output_text = "openai response"
            usage = None

        class MockClient:
            class responses:
                @staticmethod
                async def create(**kwargs):
                    return MockResponse()

        adapter = OpenAIAgentsAdapter()
        agent = adapter.wrap(MockClient(), model="gpt-4")
        state = _fresh_state()
        result = await agent.run(state, None, None)
        assert result.stop_reason == StopReason.COMPLETED
        assert "openai response" in result.messages[-1]["content"]
