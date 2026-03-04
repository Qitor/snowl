from __future__ import annotations

from pathlib import Path

from snowl.runtime.container_runtime import ContainerRuntime


def _runtime() -> ContainerRuntime:
    return ContainerRuntime(
        task_id="osworld:test",
        agent_id="osworld_official_agent",
        variant_id="default",
        task_env_type="gui",
        task_metadata={"benchmark": "osworld"},
        sample={"id": "s1", "input": "x"},
    )


def test_osworld_port_resolution_auto_allocates_unique_ports(monkeypatch) -> None:
    runtime = _runtime()
    for key in (
        "SNOWL_OSWORLD_SERVER_PORT",
        "SNOWL_OSWORLD_CHROMIUM_PORT",
        "SNOWL_OSWORLD_VNC_PORT",
        "SNOWL_OSWORLD_VLC_PORT",
    ):
        monkeypatch.delenv(key, raising=False)

    # Simulate default ports busy to force allocation to next free values.
    busy = {5000, 9222, 8006, 8080}
    monkeypatch.setattr(runtime, "_is_tcp_port_available", lambda p: int(p) not in busy)

    ports, explicit = runtime._resolve_osworld_ports()
    assert explicit is False
    assert set(ports.keys()) == {5000, 9222, 8006, 8080}
    assert len(set(ports.values())) == 4
    assert ports[5000] != 5000
    assert ports[9222] != 9222
    assert ports[8006] != 8006
    assert ports[8080] != 8080


def test_osworld_prepare_retries_when_port_conflict(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime()
    vm = tmp_path / "Ubuntu.qcow2"
    vm.write_bytes(b"vm")

    monkeypatch.setenv("SNOWL_OSWORLD_START_RETRIES", "2")
    monkeypatch.setattr(runtime, "_ensure_docker_available", lambda **kwargs: "docker")
    monkeypatch.setattr(
        runtime,
        "_resolve_osworld_boot_inputs",
        lambda: ({}, {str(vm): "/System.qcow2:ro"}, False, {"source": "auto_cached_vm"}),
    )
    monkeypatch.setattr(runtime, "_resolve_osworld_cap_add", lambda: ["NET_ADMIN"])

    port_batches = iter(
        [
            ({5000: 5000, 9222: 9222, 8006: 8006, 8080: 8080}, False),
            ({5000: 15000, 9222: 19222, 8006: 18006, 8080: 18080}, False),
        ]
    )
    monkeypatch.setattr(runtime, "_resolve_osworld_ports", lambda: next(port_batches))

    calls: list[dict[int, int]] = []

    def fake_start_container(self, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(dict(kwargs.get("ports") or {}))
        if len(calls) == 1:
            return {
                "exit_code": 125,
                "stdout": "",
                "stderr": "Bind for 0.0.0.0:5000 failed: port is already allocated",
                "ready": False,
            }
        return {
            "exit_code": 0,
            "stdout": "a" * 64,
            "stderr": "",
            "ready": True,
        }

    monkeypatch.setattr("snowl.runtime.container_runtime.GuiEnv.start_container", fake_start_container)
    monkeypatch.setattr(
        "snowl.runtime.container_runtime.GuiEnv.container_logs",
        lambda self, **kwargs: {"stdout": "", "stderr": "port is already allocated", "exit_code": 0},
    )
    monkeypatch.setattr(
        "snowl.runtime.container_runtime.GuiEnv.stop_container",
        lambda self, **kwargs: {"exit_code": 0},
    )

    session = runtime._prepare_osworld()
    assert session.kind == "gui_container"
    assert len(calls) == 2
    assert calls[0][5000] == 5000
    assert calls[1][5000] == 15000
