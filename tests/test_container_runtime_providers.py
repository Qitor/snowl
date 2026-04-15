from __future__ import annotations

import asyncio
from pathlib import Path

from snowl.runtime.container_contract import resolve_runtime_container_spec
from snowl.runtime.container_providers import (
    ContainerProviderContext,
    ContainerProviderRegistry,
    ContainerSession,
    OSWorldProvider,
    TerminalBenchProvider,
    default_container_provider_registry,
)
from snowl.runtime.container_runtime import ContainerRuntime


def _context_spec(*, benchmark: str, requires_container: bool, startup: dict[str, object] | None = None):
    return resolve_runtime_container_spec(
        task_metadata={
            "benchmark": benchmark,
            "runtime_container": {
                "benchmark": benchmark,
                "provider_name": benchmark,
                "requires_container": requires_container,
                "cleanup_policy": "destroy_on_release",
            },
        },
        sample={
            "id": "sample-1",
            "metadata": {
                "runtime_container": {
                    "benchmark": benchmark,
                    "provider_name": benchmark,
                    "requires_container": requires_container,
                    "startup": dict(startup or {}),
                }
            },
        },
    )


def test_container_runtime_uses_provider_registry() -> None:
    events: list[dict[str, object]] = []

    class _DummyProvider:
        name = "dummy"

        def describe_requirements(self, context: ContainerProviderContext) -> dict[str, object]:
            return {
                "benchmark": "dummybench",
                "requires_container": True,
                "requires_build": False,
                "spec_hash": context.container_spec.spec_hash,
                "prepare_provider_ids": (),
            }

        async def prepare(self, context: ContainerProviderContext) -> ContainerSession:
            context.emit_event({"event": "dummy.prepare"})
            return ContainerSession(kind="dummy", env={"ok": True}, benchmark="dummy")

        async def close(self, context: ContainerProviderContext, session: ContainerSession) -> dict[str, object]:
            _ = session
            context.emit_event({"event": "dummy.close"})
            return {"closed": True}

    registry = ContainerProviderRegistry()
    registry.register("dummybench", _DummyProvider())

    runtime = ContainerRuntime(
        task_id="task-1",
        agent_id="agent-1",
        variant_id="v1",
        task_env_type="local",
        task_metadata={
            "benchmark": "dummybench",
            "runtime_container": {
                "benchmark": "dummybench",
                "provider_name": "dummybench",
                "requires_container": True,
            },
        },
        sample={
            "id": "s1",
            "metadata": {
                "runtime_container": {
                    "benchmark": "dummybench",
                    "provider_name": "dummybench",
                    "requires_container": True,
                }
            },
        },
        emit=events.append,
        provider_registry=registry,
    )

    session = runtime.prepare()
    assert session is not None
    assert session.kind == "dummy"
    closed = runtime.close()
    assert closed == {"closed": True}
    assert [evt["event"] for evt in events] == ["dummy.prepare", "dummy.close"]


def test_container_runtime_returns_none_for_unknown_benchmark() -> None:
    runtime = ContainerRuntime(
        task_id="task-1",
        agent_id="agent-1",
        variant_id="v1",
        task_env_type="local",
        task_metadata={"benchmark": "unknown"},
        sample={"id": "s1"},
    )
    assert runtime.prepare() is None
    assert runtime.close() is None


def test_container_runtime_requires_contract_for_container_prepare() -> None:
    registry = ContainerProviderRegistry()
    registry.register("dummybench", object())  # type: ignore[arg-type]

    runtime = ContainerRuntime(
        task_id="task-1",
        agent_id="agent-1",
        variant_id="v1",
        task_env_type="local",
        task_metadata={"benchmark": "dummybench"},
        sample={"id": "s1"},
        provider_registry=registry,
    )

    assert runtime.prepare() is None


def test_default_provider_registry_contains_terminalbench_and_osworld() -> None:
    registry = default_container_provider_registry()
    assert registry.resolve("terminalbench") is not None
    assert registry.resolve("osworld") is not None


def test_terminalbench_provider_emits_compatible_lifecycle_events(monkeypatch, tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text("services: {client: {image: busybox}}\n", encoding="utf-8")

    events: list[dict[str, object]] = []

    class _FakeTerminalEnv:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.compose_project = kwargs.get("compose_project")
            self.compose_file = kwargs.get("compose_file")
            self.compose_service = kwargs.get("compose_service")
            self.compose_build = bool(kwargs.get("compose_build", True))
            self.compose_env = dict(kwargs.get("compose_env") or {})
            self.use_docker_compose = bool(kwargs.get("use_docker_compose", False))

        def compose_up(self, on_event=None):  # type: ignore[no-untyped-def]
            if callable(on_event):
                on_event({"event": "runtime.env.command.start", "command_text": "docker compose up -d"})
                on_event({"event": "runtime.env.command.finish", "command_text": "docker compose up -d", "exit_code": 0})
            return {
                "event": "terminal.compose.up",
                "command": ["docker", "compose", "up", "-d"],
                "exit_code": 0,
                "duration_ms": 12,
                "stdout": "ok",
                "stderr": "",
                "build": {
                    "command": ["docker", "compose", "build"],
                    "exit_code": 0,
                    "duration_ms": 11,
                    "stdout": "build ok",
                    "stderr": "",
                },
            }

        def compose_down(self, on_event=None):  # type: ignore[no-untyped-def]
            if callable(on_event):
                on_event({"event": "runtime.env.command.finish", "command_text": "docker compose down", "exit_code": 0})
            return {
                "event": "terminal.compose.down",
                "command": ["docker", "compose", "down"],
                "exit_code": 0,
                "duration_ms": 5,
                "stdout": "down ok",
                "stderr": "",
            }

    monkeypatch.setattr("snowl.runtime.container_providers.TerminalEnv", _FakeTerminalEnv)
    monkeypatch.setattr("snowl.runtime.container_providers.shutil.which", lambda _name: "/usr/bin/docker")

    provider = TerminalBenchProvider()
    context = ContainerProviderContext(
        run_id="run-1",
        trial_id="trial-1",
        task_id="task-1",
        agent_id="agent-1",
        variant_id="v1",
        task_env_type="terminal",
        task_metadata={"benchmark": "terminalbench"},
        sample={
            "id": "sample-1",
            "metadata": {
                "task_id": "tb-task",
                "task_root": str(tmp_path),
                "docker_compose_path": str(compose_file),
                "compose_service": "client",
            },
        },
        container_spec=_context_spec(
            benchmark="terminalbench",
            requires_container=True,
            startup={
                "compose_file": str(compose_file),
                "compose_service": "client",
                "task_root": str(tmp_path),
                "task_id": "tb-task",
                "safe_task": "tb-task",
                "safe_sample": "sample-1",
                "safe_variant": "v1",
            },
        ),
        emit=events.append,
    )

    session = asyncio.run(provider.prepare(context))
    assert session.kind == "terminal_compose"
    assert session.env.compose_env["T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME"].endswith("-v1")
    assert session.env.compose_env["T_BENCH_TASK_DOCKER_NAME_PREFIX"].endswith("__v1")
    assert session.env.compose_env["T_BENCH_TASK_LOGS_PATH"].endswith("/sample-1/v1")
    assert session.env.compose_env["T_BENCH_TASK_AGENT_LOGS_PATH"].endswith("/sample-1/v1")
    asyncio.run(provider.close(context, session))

    names = [str(evt.get("event")) for evt in events]
    assert "terminalbench.container.starting" in names
    assert "terminalbench.container.build" in names
    assert "terminalbench.container.started" in names
    assert "terminalbench.container.stopping" in names
    assert "terminalbench.container.stopped" in names
    assert "runtime.env.command.finish" in names


def test_terminalbench_provider_isolates_resources_per_variant(monkeypatch, tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text("services: {client: {image: busybox}}\n", encoding="utf-8")

    class _FakeTerminalEnv:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.compose_project = kwargs.get("compose_project")
            self.compose_env = dict(kwargs.get("compose_env") or {})
            self.compose_file = kwargs.get("compose_file")
            self.compose_service = kwargs.get("compose_service")
            self.compose_build = bool(kwargs.get("compose_build", True))
            self.use_docker_compose = bool(kwargs.get("use_docker_compose", False))

        def compose_up(self, on_event=None):  # type: ignore[no-untyped-def]
            _ = on_event
            return {"event": "terminal.compose.up", "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""}

        def compose_down(self, on_event=None):  # type: ignore[no-untyped-def]
            _ = on_event
            return {"event": "terminal.compose.down", "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": ""}

    monkeypatch.setattr("snowl.runtime.container_providers.TerminalEnv", _FakeTerminalEnv)
    monkeypatch.setattr("snowl.runtime.container_providers.shutil.which", lambda _name: "/usr/bin/docker")

    provider = TerminalBenchProvider()

    def _context(variant_id: str) -> ContainerProviderContext:
        return ContainerProviderContext(
            run_id="run-1",
            trial_id=f"trial-{variant_id}",
            task_id="task-1",
            agent_id="agent-1",
            variant_id=variant_id,
            task_env_type="terminal",
            task_metadata={"benchmark": "terminalbench"},
            sample={
                "id": "sample-1",
                "metadata": {
                    "task_id": "tb-task",
                    "task_root": str(tmp_path),
                    "docker_compose_path": str(compose_file),
                    "compose_service": "client",
                },
            },
            container_spec=_context_spec(
                benchmark="terminalbench",
                requires_container=True,
                startup={
                    "compose_file": str(compose_file),
                    "compose_service": "client",
                    "task_root": str(tmp_path),
                    "task_id": "tb-task",
                    "safe_task": "tb-task",
                    "safe_sample": "sample-1",
                    "safe_variant": variant_id,
                },
            ),
            emit=lambda _evt: None,
        )

    session_v1 = asyncio.run(provider.prepare(_context("v1")))
    session_v2 = asyncio.run(provider.prepare(_context("v2")))

    assert session_v1.env.compose_project != session_v2.env.compose_project
    assert session_v1.env.compose_env["T_BENCH_TASK_LOGS_PATH"] != session_v2.env.compose_env["T_BENCH_TASK_LOGS_PATH"]
    assert session_v1.env.compose_env["T_BENCH_TASK_AGENT_LOGS_PATH"] != session_v2.env.compose_env["T_BENCH_TASK_AGENT_LOGS_PATH"]
    assert session_v1.env.compose_env["T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME"] != session_v2.env.compose_env["T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME"]


def test_osworld_provider_prepare_and_close_emit_events(monkeypatch) -> None:
    events: list[dict[str, object]] = []

    class _FakeGuiEnv:
        def stop_container(self, *, on_event=None):  # type: ignore[no-untyped-def]
            if callable(on_event):
                on_event({"event": "runtime.env.command.finish", "command_text": "docker rm -f c1", "exit_code": 0})
            return {"event": "gui.container.stop", "exit_code": 0}

    class _FakeLauncher:
        def __init__(self, *, repo_root, emit=None, settings=None):  # type: ignore[no-untyped-def]
            _ = repo_root
            self._emit = emit
            self._settings = settings

        def prepare(self, *, docker_path: str):
            if callable(self._emit):
                self._emit({"event": "osworld.container.started", "phase": "env", "docker_path": docker_path})
            return type("Prepared", (), {"env": _FakeGuiEnv(), "metadata": {"image": "img"}})()

    monkeypatch.setattr("snowl.runtime.container_providers.OSWorldContainerLauncher", _FakeLauncher)
    monkeypatch.setattr("snowl.runtime.container_providers.shutil.which", lambda _name: "/usr/bin/docker")

    provider = OSWorldProvider()
    context = ContainerProviderContext(
        run_id="run-1",
        trial_id="trial-1",
        task_id="task-1",
        agent_id="agent-1",
        variant_id="v1",
        task_env_type="gui",
        task_metadata={"benchmark": "osworld"},
        sample={"id": "sample-1"},
        container_spec=_context_spec(
            benchmark="osworld",
            requires_container=True,
            startup={"image": "happysixd/osworld-docker"},
        ),
        emit=events.append,
    )

    session = asyncio.run(provider.prepare(context))
    assert session.kind == "gui_container"
    close_out = asyncio.run(provider.close(context, session))
    assert close_out == {"event": "gui.container.stop", "exit_code": 0}

    names = [str(evt.get("event")) for evt in events]
    assert "osworld.container.started" in names
    assert "osworld.container.stopping" in names
    assert "osworld.container.stopped" in names
    assert "runtime.env.command.finish" in names
