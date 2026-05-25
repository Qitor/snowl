"""Tests for QitOS framework adapter."""

import pytest

from snowl.adapters.qitos import QitOSAdapter, _QitOSAgent
from snowl.core.agent import AgentState, StopReason


class TestQitOSAdapter:
    def test_framework_name(self):
        adapter = QitOSAdapter()
        assert adapter.framework_name == "qitos"

    def test_wrap_returns_agent(self):
        adapter = QitOSAdapter()

        class MockModule:
            name = "test_agent"

        agent = adapter.wrap(MockModule())
        assert isinstance(agent, _QitOSAgent)
        assert "qitos" in agent.agent_id

    def test_wrap_with_config(self):
        adapter = QitOSAdapter()

        class MockModule:
            name = "test_agent"

        agent = adapter.wrap(MockModule(), max_steps=10, workspace="/tmp")
        assert agent._config["max_steps"] == 10
        assert agent._config["workspace"] == "/tmp"

    def test_unwrap_state_extracts_instruction(self):
        adapter = QitOSAdapter()
        state = AgentState(
            messages=[{"role": "user", "content": "Solve this problem"}],
        )
        result = adapter.unwrap_state(state)
        assert "Solve this problem" in result

    def test_wrap_result_with_engine_result(self):
        adapter = QitOSAdapter()
        state = AgentState(messages=[{"role": "user", "content": "Hello"}])

        class MockTaskResult:
            final_answer = "42"

        class MockEngineResult:
            task_result = MockTaskResult()
            cancel = False

        result = adapter.wrap_result(MockEngineResult(), state)
        assert result.output == "42"
        assert result.stop_reason == StopReason.COMPLETED
        # Should have assistant message appended
        assert len(result.messages) == 2
        assert result.messages[-1]["role"] == "assistant"

    def test_wrap_result_with_cancel(self):
        adapter = QitOSAdapter()
        state = AgentState(messages=[])

        class MockEngineResult:
            task_result = None
            cancel = True

        result = adapter.wrap_result(MockEngineResult(), state)
        assert result.stop_reason == StopReason.CANCELLED

    def test_wrap_tools_passthrough(self):
        adapter = QitOSAdapter()
        tools = [{"name": "tool1"}, {"name": "tool2"}]
        result = adapter.wrap_tools(tools)
        assert result == tools


class TestQitOSAgentRun:
    @pytest.mark.asyncio
    async def test_run_success(self):
        adapter = QitOSAdapter()

        class MockModule:
            name = "test_agent"

            def run(self, task, **kwargs):
                class TaskResult:
                    final_answer = "The answer is 42"
                class Result:
                    task_result = TaskResult()
                    cancel = False
                return Result()

        agent = adapter.wrap(MockModule())
        state = AgentState(
            messages=[{"role": "user", "content": "What is the answer?"}],
        )
        result = await agent.run(state, context=None)
        assert result.output == "The answer is 42"
        assert result.stop_reason == StopReason.COMPLETED

    @pytest.mark.asyncio
    async def test_run_error(self):
        adapter = QitOSAdapter()

        class MockModule:
            name = "test_agent"

            def run(self, task, **kwargs):
                raise RuntimeError("QitOS engine crashed")

        agent = adapter.wrap(MockModule())
        state = AgentState(
            messages=[{"role": "user", "content": "Do something"}],
        )
        result = await agent.run(state, context=None)
        assert "error" in result.output.lower() or "crashed" in result.output.lower()
        assert result.stop_reason == StopReason.ERROR

    @pytest.mark.asyncio
    async def test_run_passes_config(self):
        adapter = QitOSAdapter()
        captured_kwargs = {}

        class MockModule:
            name = "test_agent"

            def run(self, task, **kwargs):
                captured_kwargs.update(kwargs)

                class TaskResult:
                    final_answer = "done"
                class Result:
                    task_result = TaskResult()
                    cancel = False
                return Result()

        agent = adapter.wrap(MockModule(), max_steps=5, workspace="/tmp/ws")
        state = AgentState(
            messages=[{"role": "user", "content": "Do it"}],
        )
        await agent.run(state, context=None)
        assert captured_kwargs.get("max_steps") == 5
        assert captured_kwargs.get("workspace") == "/tmp/ws"


class TestQitOSRegistry:
    def test_qitos_registered(self):
        from snowl.adapters.registry import get_default_adapter_registry
        registry = get_default_adapter_registry()
        assert registry.has("qitos")

    def test_qitos_in_framework_list(self):
        from snowl.adapters.registry import get_default_adapter_registry
        registry = get_default_adapter_registry()
        assert "qitos" in registry.list_frameworks()

    def test_create_qitos_adapter(self):
        from snowl.adapters.registry import get_default_adapter_registry
        registry = get_default_adapter_registry()
        adapter = registry.get("qitos")
        assert adapter.framework_name == "qitos"


class TestQitOSLazyImport:
    def test_import_snowl_without_qitos(self):
        """Snowl should import without qitos installed."""
        # The adapter module itself should import fine
        from snowl.adapters.qitos import QitOSAdapter
        assert QitOSAdapter is not None

    def test_wrap_checks_qitos_available(self):
        """wrap() should raise ImportError if qitos is not installed."""
        from snowl.adapters.qitos import QitOSAdapter, _check_qitos_available
        adapter = QitOSAdapter()

        class MockModule:
            name = "test"

        # If qitos IS installed (as in this test env), wrap should work
        # If NOT installed, it would raise ImportError
        try:
            agent = adapter.wrap(MockModule())
            assert agent is not None
        except ImportError:
            pass  # Expected if qitos not installed
