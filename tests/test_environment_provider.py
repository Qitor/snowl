"""Tests for EnvironmentProvider ABC, built-in providers, and registry."""

import pytest

from snowl.core.env import SandboxSpec
from snowl.envs.provider import (
    DockerProvider,
    EnvironmentCapabilities,
    EnvironmentHandle,
    EnvironmentProvider,
    EnvironmentProviderRegistry,
    LocalProvider,
    default_environment_provider_registry,
)


# ---------------------------------------------------------------------------
# EnvironmentCapabilities
# ---------------------------------------------------------------------------

class TestEnvironmentCapabilities:
    def test_defaults(self):
        caps = EnvironmentCapabilities()
        assert caps.supported_ops == ()
        assert not caps.supports_networking
        assert not caps.supports_gui
        assert caps.max_duration_seconds is None
        assert caps.max_concurrent is None


# ---------------------------------------------------------------------------
# EnvironmentHandle
# ---------------------------------------------------------------------------

class TestEnvironmentHandle:
    def test_basic_construction(self):
        h = EnvironmentHandle(environment_id="test-1", provider_name="local")
        assert h.environment_id == "test-1"
        assert h.provider_name == "local"
        assert h.metadata == {}

    def test_with_metadata(self):
        h = EnvironmentHandle(
            environment_id="c-123",
            provider_name="docker",
            metadata={"image": "test:1"},
        )
        assert h.metadata["image"] == "test:1"


# ---------------------------------------------------------------------------
# DockerProvider
# ---------------------------------------------------------------------------

class TestDockerProvider:
    def test_name(self):
        assert DockerProvider().name == "docker"

    def test_is_environment_provider(self):
        assert isinstance(DockerProvider(), EnvironmentProvider)

    def test_capabilities(self):
        caps = DockerProvider().describe_capabilities()
        assert "process.run" in caps.supported_ops


# ---------------------------------------------------------------------------
# LocalProvider
# ---------------------------------------------------------------------------

class TestLocalProvider:
    def test_name(self):
        assert LocalProvider().name == "local"

    def test_is_environment_provider(self):
        assert isinstance(LocalProvider(), EnvironmentProvider)

    @pytest.mark.asyncio
    async def test_prepare(self):
        provider = LocalProvider()
        spec = SandboxSpec(image="test:1")
        handle = await provider.prepare(spec)
        assert handle.provider_name == "local"
        assert handle.environment_id.startswith("local-")

    @pytest.mark.asyncio
    async def test_teardown(self):
        provider = LocalProvider()
        spec = SandboxSpec(image="test:1")
        handle = await provider.prepare(spec)
        result = await provider.teardown(handle)
        assert result["provider"] == "local"

    def test_capabilities(self):
        caps = LocalProvider().describe_capabilities()
        assert "process.run" in caps.supported_ops
        assert caps.supports_networking


# ---------------------------------------------------------------------------
# EnvironmentProviderRegistry
# ---------------------------------------------------------------------------

class TestEnvironmentProviderRegistry:
    def test_register_and_get(self):
        registry = EnvironmentProviderRegistry()
        registry.register("local", LocalProvider)
        provider = registry.get("local")
        assert isinstance(provider, LocalProvider)

    def test_has(self):
        registry = EnvironmentProviderRegistry()
        registry.register("local", LocalProvider)
        assert registry.has("local")
        assert not registry.has("docker")

    def test_list_providers(self):
        registry = EnvironmentProviderRegistry()
        registry.register("local", LocalProvider)
        registry.register("docker", DockerProvider)
        assert registry.list_providers() == ["docker", "local"]

    def test_get_unknown_raises(self):
        registry = EnvironmentProviderRegistry()
        with pytest.raises(KeyError, match="No environment provider"):
            registry.get("unknown")

    def test_register_invalid_name(self):
        registry = EnvironmentProviderRegistry()
        with pytest.raises(ValueError):
            registry.register("", LocalProvider)

    def test_register_invalid_class(self):
        registry = EnvironmentProviderRegistry()
        with pytest.raises(TypeError):
            registry.register("bad", str)

    def test_from_entry_points(self):
        # Should not raise even with no entry points installed
        registry = EnvironmentProviderRegistry.from_entry_points()
        assert isinstance(registry, EnvironmentProviderRegistry)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    def test_has_docker_and_local(self):
        registry = default_environment_provider_registry()
        assert registry.has("docker")
        assert registry.has("local")

    def test_docker_provider(self):
        registry = default_environment_provider_registry()
        provider = registry.get("docker")
        assert isinstance(provider, DockerProvider)

    def test_local_provider(self):
        registry = default_environment_provider_registry()
        provider = registry.get("local")
        assert isinstance(provider, LocalProvider)
