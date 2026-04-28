from __future__ import annotations

import asyncio

from snowl.runtime.container_contract import resolve_runtime_container_spec
from snowl.runtime.container_lifecycle import ContainerLifecycleState, RuntimeContainerLifecycleManager


def test_runtime_container_contract_merges_task_and_sample_layers() -> None:
    spec = resolve_runtime_container_spec(
        task_metadata={
            "benchmark": "terminalbench",
            "runtime_container": {
                "benchmark": "terminalbench",
                "provider_name": "terminalbench",
                "requires_container": False,
                "cleanup_policy": "destroy_on_release",
                "startup": {
                    "compose_build": True,
                    "task_root": "/repo/task",
                },
                "spec_hash_basis": {
                    "compose_build": True,
                },
            },
        },
        sample={
            "id": "sample-1",
            "metadata": {
                "runtime_container": {
                    "requires_container": True,
                    "startup": {
                        "compose_file": "/repo/task/docker-compose.yaml",
                        "compose_service": "client",
                    },
                    "spec_hash_basis": {
                        "compose_file": "/repo/task/docker-compose.yaml",
                    },
                }
            },
        },
    )

    assert spec.benchmark == "terminalbench"
    assert spec.provider_name == "terminalbench"
    assert spec.requires_container is True
    assert spec.cleanup_policy == "destroy_on_release"
    assert spec.startup["compose_build"] is True
    assert spec.startup["compose_service"] == "client"
    assert spec.spec_hash is not None


def test_runtime_container_contract_v2_fields_and_legacy_startup() -> None:
    spec = resolve_runtime_container_spec(
        task_metadata={
            "benchmark": "ipi_coding_agent",
            "runtime_container": {
                "provider_name": "docker_container",
                "requires_container": True,
                "network": "disabled",
                "env": {"A": "1"},
                "workspace": {"enabled": True, "repo_files": {"a.txt": "x"}},
                "resource_limits": {"start_timeout_seconds": 10},
            },
        },
        sample={
            "id": "sample-1",
            "metadata": {
                "runtime_container": {
                    "startup": {"image": "python:3.12", "verification_command": "pytest -q"},
                    "init_command": "pip install -e .",
                    "env": {"B": "2"},
                }
            },
        },
    )

    assert spec.provider_name == "docker_container"
    assert spec.network == "disabled"
    assert spec.env == {"A": "1", "B": "2"}
    assert spec.workspace["enabled"] is True
    assert spec.init_command == "pip install -e ."
    assert spec.check_command == "pytest -q"
    assert spec.resource_limits["start_timeout_seconds"] == 10


def test_runtime_container_lifecycle_register_release_destroy_default() -> None:
    torn_down: list[str] = []
    emitted: list[dict[str, object]] = []

    manager = RuntimeContainerLifecycleManager(
        run_id="run-1",
        emit=lambda evt: emitted.append(dict(evt)),
    )

    async def _teardown():
        torn_down.append("done")
        return {"closed": True}

    async def _run() -> None:
        resource_id = manager.register_container(
            trial_id="trial-1",
            benchmark="terminalbench",
            provider_name="terminalbench",
            spec_hash="abc",
            cleanup_policy="destroy_on_release",
            debug_preserve=False,
            container_id="container-1",
            compose_project="proj-1",
            compose_file="/tmp/docker-compose.yaml",
            session_kind="terminal_compose",
            provider_metadata={"origin": "test"},
            teardown=_teardown,
        )
        manager.lease_resource(resource_id, trial_id="trial-1")
        await manager.release_resource(
            resource_id,
            trial_id="trial-1",
            outcome_status="success",
        )

        summary = manager.snapshot()
        assert summary["containers_created"] == 1
        assert summary["containers_leased"] == 1
        assert summary["containers_destroyed"] == 1
        assert summary["suspected_leaked_resources"] == 0

    asyncio.run(_run())

    assert torn_down == ["done"]
    events = [str(evt.get("event")) for evt in emitted]
    assert "runtime.resource.registered" in events
    assert "runtime.resource.leased" in events
    assert "runtime.resource.released" in events
    assert "runtime.resource.teardown.finish" in events


def test_runtime_container_lifecycle_preserves_failed_containers_only_when_enabled() -> None:
    torn_down: list[str] = []

    manager = RuntimeContainerLifecycleManager(
        run_id="run-1",
        keep_failed_containers=True,
    )

    async def _teardown():
        torn_down.append("done")
        return {"closed": True}

    async def _run() -> None:
        resource_id = manager.register_container(
            trial_id="trial-1",
            benchmark="osworld",
            provider_name="osworld",
            spec_hash="abc",
            cleanup_policy="destroy_on_release",
            debug_preserve=False,
            container_id="container-1",
            compose_project=None,
            compose_file=None,
            session_kind="gui_container",
            provider_metadata={},
            teardown=_teardown,
        )
        manager.lease_resource(resource_id, trial_id="trial-1")
        await manager.release_resource(
            resource_id,
            trial_id="trial-1",
            outcome_status="error",
        )
        summary = manager.snapshot()
        assert summary["containers_preserved"] == 1
        assert summary["containers_destroyed"] == 0
        assert summary["surviving_resources"][0]["lifecycle_state"] == ContainerLifecycleState.DIRTY.value
        assert summary["surviving_resources"][0]["debug_preserve"] is True

    asyncio.run(_run())
    assert torn_down == []
