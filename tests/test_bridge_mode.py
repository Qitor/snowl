"""Tests for bridge mode: config, usage accumulator, generate, and context manager."""

import pytest

from snowl.bridges._config import (
    BridgeConfig,
    BridgeUsageAccumulator,
    get_bridge_config,
    set_bridge_config,
    reset_bridge_config,
    get_usage_accumulator,
    set_usage_accumulator,
    reset_usage_accumulator,
    record_model_call,
)


# ---------------------------------------------------------------------------
# BridgeConfig
# ---------------------------------------------------------------------------

class TestBridgeConfig:
    def test_default(self):
        cfg = BridgeConfig()
        assert not cfg.enabled
        assert cfg.model_client is None
        assert cfg.provider_id == "default"

    def test_with_model_client(self):
        cfg = BridgeConfig(enabled=True, model_client="mock_client")
        assert cfg.enabled
        assert cfg.model_client == "mock_client"


# ---------------------------------------------------------------------------
# BridgeUsageAccumulator
# ---------------------------------------------------------------------------

class TestBridgeUsageAccumulator:
    def test_initial_state(self):
        acc = BridgeUsageAccumulator()
        assert acc.call_count == 0
        assert acc.input_tokens == 0
        assert acc.output_tokens == 0
        assert acc.total_tokens == 0
        assert acc.call_timings_ms == []


# ---------------------------------------------------------------------------
# ContextVar lifecycle
# ---------------------------------------------------------------------------

class TestBridgeConfigContextVar:
    def test_default_is_none(self):
        assert get_bridge_config() is None

    def test_set_and_get(self):
        cfg = BridgeConfig(enabled=True, model_client="test")
        token = set_bridge_config(cfg)
        assert get_bridge_config() is cfg
        reset_bridge_config(token)
        assert get_bridge_config() is None

    def test_nested(self):
        cfg1 = BridgeConfig(enabled=True, provider_id="outer")
        token1 = set_bridge_config(cfg1)
        assert get_bridge_config().provider_id == "outer"

        cfg2 = BridgeConfig(enabled=True, provider_id="inner")
        token2 = set_bridge_config(cfg2)
        assert get_bridge_config().provider_id == "inner"

        reset_bridge_config(token2)
        assert get_bridge_config().provider_id == "outer"
        reset_bridge_config(token1)
        assert get_bridge_config() is None


class TestUsageAccumulatorContextVar:
    def test_default_is_none(self):
        assert get_usage_accumulator() is None

    def test_set_and_get(self):
        acc = BridgeUsageAccumulator()
        token = set_usage_accumulator(acc)
        assert get_usage_accumulator() is acc
        reset_usage_accumulator(token)
        assert get_usage_accumulator() is None


# ---------------------------------------------------------------------------
# record_model_call
# ---------------------------------------------------------------------------

class TestRecordModelCall:
    def test_records_into_accumulator(self):
        acc = BridgeUsageAccumulator()
        token = set_usage_accumulator(acc)
        try:
            record_model_call(input_tokens=10, output_tokens=20, total_tokens=30, duration_ms=100)
            assert acc.call_count == 1
            assert acc.input_tokens == 10
            assert acc.output_tokens == 20
            assert acc.total_tokens == 30
            assert acc.call_timings_ms == [100]
        finally:
            reset_usage_accumulator(token)

    def test_no_accumulator_no_error(self):
        # Should not raise when no accumulator is set
        record_model_call(input_tokens=10, output_tokens=20, total_tokens=30, duration_ms=100)

    def test_accumulates_multiple_calls(self):
        acc = BridgeUsageAccumulator()
        token = set_usage_accumulator(acc)
        try:
            record_model_call(input_tokens=10, output_tokens=5, total_tokens=15, duration_ms=50)
            record_model_call(input_tokens=20, output_tokens=10, total_tokens=30, duration_ms=80)
            assert acc.call_count == 2
            assert acc.input_tokens == 30
            assert acc.output_tokens == 15
            assert acc.total_tokens == 45
            assert acc.call_timings_ms == [50, 80]
        finally:
            reset_usage_accumulator(token)


# ---------------------------------------------------------------------------
# bridge_generate
# ---------------------------------------------------------------------------

class TestBridgeGenerate:
    @pytest.mark.asyncio
    async def test_generate_calls_model_client(self):
        from snowl.bridges._generate import bridge_generate
        from snowl.core.agent import AgentState

        class MockResponse:
            message = type("M", (), {"content": "Hello"})()
            usage = type("U", (), {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})()

        class MockClient:
            async def generate(self, messages, **kwargs):
                return MockResponse()

        gen_fn = bridge_generate(MockClient())
        state = AgentState(messages=[{"role": "user", "content": "Hi"}])
        result = await gen_fn(state)
        assert len(result.messages) == 2
        assert result.messages[-1]["role"] == "assistant"
        assert result.messages[-1]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_generate_records_usage(self):
        from snowl.bridges._generate import bridge_generate
        from snowl.core.agent import AgentState

        class MockResponse:
            message = type("M", (), {"content": "test"})()
            usage = type("U", (), {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8})()

        class MockClient:
            async def generate(self, messages, **kwargs):
                return MockResponse()

        acc = BridgeUsageAccumulator()
        token = set_usage_accumulator(acc)
        try:
            gen_fn = bridge_generate(MockClient())
            state = AgentState(messages=[{"role": "user", "content": "Hi"}])
            await gen_fn(state)
            assert acc.call_count == 1
            assert acc.input_tokens == 5
        finally:
            reset_usage_accumulator(token)


# ---------------------------------------------------------------------------
# snowl_bridge() context manager
# ---------------------------------------------------------------------------

class TestSnowlBridge:
    @pytest.mark.asyncio
    async def test_bridge_lifecycle(self):
        from snowl.bridges import snowl_bridge

        class MockClient:
            async def generate(self, messages, **kwargs):
                return None

        async with snowl_bridge(model_client=MockClient()) as handle:
            assert get_bridge_config() is not None
            assert get_bridge_config().enabled
            assert get_usage_accumulator() is not None

        # After context, bridge should be deactivated
        assert get_bridge_config() is None or not get_bridge_config().enabled
        assert get_usage_accumulator() is None

    @pytest.mark.asyncio
    async def test_bridge_usage(self):
        from snowl.bridges import snowl_bridge

        class MockClient:
            async def generate(self, messages, **kwargs):
                return None

        async with snowl_bridge(model_client=MockClient()) as handle:
            record_model_call(input_tokens=100, output_tokens=50, total_tokens=150, duration_ms=200)
            usage = handle.usage()
            assert usage["call_count"] == 1
            assert usage["input_tokens"] == 100
            assert usage["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_bridge_deactivated_after_context(self):
        from snowl.bridges import snowl_bridge

        class MockClient:
            async def generate(self, messages, **kwargs):
                return None

        assert get_bridge_config() is None or not get_bridge_config().enabled

        async with snowl_bridge(model_client=MockClient()):
            pass

        # Should be back to default state
        cfg = get_bridge_config()
        assert cfg is None or not cfg.enabled


# ---------------------------------------------------------------------------
# Patch install/uninstall (no-op when SDK not available)
# ---------------------------------------------------------------------------

class TestPatches:
    def test_openai_patch_no_error_without_sdk(self):
        # This should not raise even if openai is not installed
        from snowl.bridges._patch_openai import patch_openai, unpatch_openai
        patch_openai()  # idempotent, no error
        unpatch_openai()  # no error

    def test_anthropic_patch_no_error_without_sdk(self):
        from snowl.bridges._patch_anthropic import patch_anthropic, unpatch_anthropic
        patch_anthropic()  # idempotent, no error
        unpatch_anthropic()  # no error
