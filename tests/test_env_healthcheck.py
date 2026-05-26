"""Tests for HealthStatus and HealthcheckProvider."""

import pytest

from snowl.core.env import HealthStatus, HealthcheckProvider


# ---------------------------------------------------------------------------
# HealthStatus
# ---------------------------------------------------------------------------

class TestHealthStatus:
    def test_healthy(self):
        hs = HealthStatus(ready=True, checks={"network": True, "disk": True})
        assert hs.ready is True
        assert all(hs.checks.values())

    def test_unhealthy(self):
        hs = HealthStatus(ready=False, checks={"network": True, "disk": False}, message="disk full")
        assert hs.ready is False
        assert hs.checks["disk"] is False
        assert hs.message == "disk full"

    def test_empty_checks(self):
        hs = HealthStatus(ready=True)
        assert hs.checks == {}
        assert hs.message is None

    def test_frozen(self):
        hs = HealthStatus(ready=True)
        with pytest.raises(AttributeError):
            hs.ready = False


# ---------------------------------------------------------------------------
# HealthcheckProvider protocol
# ---------------------------------------------------------------------------

class TestHealthcheckProvider:
    def test_conforming_class(self):
        class MyProvider:
            async def healthcheck(self, env_id: str) -> HealthStatus:
                return HealthStatus(ready=True, checks={"alive": True})

        assert isinstance(MyProvider(), HealthcheckProvider)

    def test_non_conforming_class(self):
        class NotAProvider:
            pass

        assert not isinstance(NotAProvider(), HealthcheckProvider)

    @pytest.mark.asyncio
    async def test_provider_returns_status(self):
        class MockProvider:
            async def healthcheck(self, env_id: str) -> HealthStatus:
                if env_id == "good":
                    return HealthStatus(ready=True, checks={"network": True})
                return HealthStatus(ready=False, checks={"network": False}, message="unreachable")

        provider = MockProvider()
        good = await provider.healthcheck("good")
        assert good.ready is True

        bad = await provider.healthcheck("bad")
        assert bad.ready is False
        assert bad.message == "unreachable"
