"""Tests for SeparatedVerifierExecutor lifecycle and verifier_spec_from_config."""

import pytest

from snowl.core.env import VerifierMode, VerifierSpec
from snowl.runtime.separated_verifier import (
    VerifierResult,
    SeparatedVerifierExecutor,
)


# ---------------------------------------------------------------------------
# VerifierResult
# ---------------------------------------------------------------------------

class TestVerifierResult:
    def test_basic_construction(self):
        r = VerifierResult(
            exit_code=0, stdout="ok", stderr="", timed_out=False, container_id="abc123"
        )
        assert r.exit_code == 0
        assert r.stdout == "ok"
        assert not r.timed_out
        assert r.container_id == "abc123"

    def test_defaults(self):
        r = VerifierResult(exit_code=1, stdout="", stderr="err", timed_out=True, container_id="x")
        assert r.artifacts_snapshot == {}
        assert r.metadata == {}

    def test_frozen(self):
        r = VerifierResult(exit_code=0, stdout="", stderr="", timed_out=False, container_id="c")
        with pytest.raises(AttributeError):
            r.exit_code = 1


# ---------------------------------------------------------------------------
# SeparatedVerifierExecutor — unit tests with mocked backend
# ---------------------------------------------------------------------------

def _make_executor(**overrides):
    """Create an executor with a SEPARATE spec and optional overrides."""
    defaults = dict(
        spec=VerifierSpec(mode=VerifierMode.SEPARATE, image="test:1"),
        run_id="r1",
        trial_id="t1",
    )
    defaults.update(overrides)
    return SeparatedVerifierExecutor(**defaults)


class TestSeparatedVerifierExecutorInit:
    def test_rejects_shared_mode(self):
        from snowl.errors import SnowlValidationError
        with pytest.raises(SnowlValidationError, match="SEPARATE"):
            SeparatedVerifierExecutor(spec=VerifierSpec(mode=VerifierMode.SHARED))

    def test_initial_state(self):
        ex = _make_executor()
        assert ex.container_id is None
        assert not ex.is_prepared


class TestSeparatedVerifierExecutorPrepare:
    @pytest.mark.asyncio
    async def test_prepare_success(self):
        ex = _make_executor()

        # Mock ContainerBackend
        class FakeBackend:
            def run(self, **kwargs):
                return {"container_id": "cnt-123", "output": ""}

        class FakeRunner:
            pass

        import snowl.runtime.separated_verifier as mod

        original_cb = None
        original_cr = None
        try:
            import snowl.envs.substrate.container_backend as cb_mod
            import snowl.envs.substrate.command_runner as cr_mod
            original_cb = cb_mod.ContainerBackend
            original_cr = cr_mod.CommandRunner

            cb_mod.ContainerBackend = lambda **kw: FakeBackend()
            cr_mod.CommandRunner = FakeRunner

            await ex.prepare()
            assert ex.is_prepared
            assert ex.container_id == "cnt-123"
        finally:
            cb_mod.ContainerBackend = original_cb
            cr_mod.CommandRunner = original_cr

    @pytest.mark.asyncio
    async def test_prepare_no_image_raises(self):
        ex = _make_executor(spec=VerifierSpec(mode=VerifierMode.SEPARATE, build_context="/tmp"))
        # image is None but build_context is set — should still require image for now
        # (build support is future work; current prepare() requires image)
        from snowl.errors import SnowlValidationError
        with pytest.raises(SnowlValidationError, match="image"):
            await ex.prepare()


class TestSeparatedVerifierExecutorTransfer:
    @pytest.mark.asyncio
    async def test_transfer_without_prepare_raises(self):
        ex = _make_executor()
        with pytest.raises(RuntimeError, match="not prepared"):
            await ex.transfer_artifacts(workspace_dir="/tmp")

    @pytest.mark.asyncio
    async def test_transfer_calls_cp(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        cp_calls = []

        class FakeBackend:
            def cp(self, **kwargs):
                cp_calls.append(kwargs)
                return {"success": True}

        ex._backend = FakeBackend()
        await ex.transfer_artifacts(workspace_dir="/host/workspace")
        assert len(cp_calls) == 1
        assert cp_calls[0]["container_id"] == "cnt-1"
        assert cp_calls[0]["dest"] == "/workspace"


class TestSeparatedVerifierExecutorRunCommand:
    @pytest.mark.asyncio
    async def test_run_without_prepare_raises(self):
        ex = _make_executor()
        with pytest.raises(RuntimeError, match="not prepared"):
            await ex.run_command("echo hello")

    @pytest.mark.asyncio
    async def test_run_command_success(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        class FakeBackend:
            def exec(self, **kwargs):
                return {"exit_code": 0, "output": "hello", "stderr": "", "timed_out": False}

        ex._backend = FakeBackend()
        result = await ex.run_command("echo hello")
        assert result.exit_code == 0
        assert result.stdout == "hello"
        assert not result.timed_out
        assert result.container_id == "cnt-1"

    @pytest.mark.asyncio
    async def test_run_command_timeout(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        class FakeBackend:
            def exec(self, **kwargs):
                return {"exit_code": -1, "output": "", "stderr": "timeout", "timed_out": True}

        ex._backend = FakeBackend()
        result = await ex.run_command("sleep 999", timeout_seconds=1)
        assert result.timed_out

    @pytest.mark.asyncio
    async def test_run_command_exception_returns_result(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        class FakeBackend:
            def exec(self, **kwargs):
                raise RuntimeError("docker crashed")

        ex._backend = FakeBackend()
        result = await ex.run_command("bad command")
        assert result.exit_code == -1
        assert result.timed_out
        assert "docker crashed" in result.stderr


class TestSeparatedVerifierExecutorTeardown:
    @pytest.mark.asyncio
    async def test_teardown_no_container(self):
        ex = _make_executor()
        result = await ex.teardown()
        assert result == {}

    @pytest.mark.asyncio
    async def test_teardown_success(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        class FakeBackend:
            def rm(self, **kwargs):
                return {"removed": True}

        ex._backend = FakeBackend()
        result = await ex.teardown()
        assert result == {"removed": True}
        assert ex.container_id is None
        assert not ex.is_prepared

    @pytest.mark.asyncio
    async def test_teardown_exception_returns_error(self):
        ex = _make_executor()
        ex._container_id = "cnt-1"

        class FakeBackend:
            def rm(self, **kwargs):
                raise RuntimeError("cannot remove")

        ex._backend = FakeBackend()
        result = await ex.teardown()
        assert "error" in result


class TestSeparatedVerifierExecutorExecute:
    @pytest.mark.asyncio
    async def test_execute_full_lifecycle(self):
        events = []
        ex = _make_executor(emit=events.append)

        class FakeBackend:
            def run(self, **kwargs):
                return {"container_id": "cnt-exec", "output": ""}

            def cp(self, **kwargs):
                return {"success": True}

            def exec(self, **kwargs):
                return {"exit_code": 0, "output": "pass", "stderr": "", "timed_out": False}

            def rm(self, **kwargs):
                return {"removed": True}

        import snowl.runtime.separated_verifier as mod
        import snowl.envs.substrate.container_backend as cb_mod
        import snowl.envs.substrate.command_runner as cr_mod

        original_cb = cb_mod.ContainerBackend
        original_cr = cr_mod.CommandRunner
        try:
            cb_mod.ContainerBackend = lambda **kw: FakeBackend()
            cr_mod.CommandRunner = lambda: None

            result = await ex.execute("python check.py", workspace_dir="/ws")
            assert result.exit_code == 0
            assert result.stdout == "pass"

            # Verify events were emitted
            event_types = [e.get("event") for e in events]
            assert "runtime.verifier.prepare" in event_types
            assert "runtime.verifier.transfer" in event_types
            assert "runtime.verifier.execute" in event_types
            assert "runtime.verifier.teardown" in event_types
        finally:
            cb_mod.ContainerBackend = original_cb
            cr_mod.CommandRunner = original_cr


class TestSeparatedVerifierExecutorEvents:
    @pytest.mark.asyncio
    async def test_events_emitted_on_prepare(self):
        events = []
        ex = _make_executor(emit=events.append)

        class FakeBackend:
            def run(self, **kwargs):
                return {"container_id": "cnt-1", "output": ""}

        import snowl.envs.substrate.container_backend as cb_mod
        import snowl.envs.substrate.command_runner as cr_mod

        original_cb = cb_mod.ContainerBackend
        original_cr = cr_mod.CommandRunner
        try:
            cb_mod.ContainerBackend = lambda **kw: FakeBackend()
            cr_mod.CommandRunner = lambda: None

            await ex.prepare()
            assert any(e.get("event") == "runtime.verifier.prepare" for e in events)
        finally:
            cb_mod.ContainerBackend = original_cb
            cr_mod.CommandRunner = original_cr

    @pytest.mark.asyncio
    async def test_error_event_on_prepare_failure(self):
        events = []
        ex = _make_executor(emit=events.append)

        class FakeBackend:
            def run(self, **kwargs):
                raise RuntimeError("docker not available")

        import snowl.envs.substrate.container_backend as cb_mod
        import snowl.envs.substrate.command_runner as cr_mod

        original_cb = cb_mod.ContainerBackend
        original_cr = cr_mod.CommandRunner
        try:
            cb_mod.ContainerBackend = lambda **kw: FakeBackend()
            cr_mod.CommandRunner = lambda: None

            with pytest.raises(RuntimeError):
                await ex.prepare()
            error_events = [e for e in events if e.get("event") == "runtime.verifier.error"]
            assert len(error_events) == 1
            assert error_events[0]["step"] == "prepare"
        finally:
            cb_mod.ContainerBackend = original_cb
            cr_mod.CommandRunner = original_cr