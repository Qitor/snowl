from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.osworld import container as osw_container
from snowl.benchmarks.osworld.container import OSWorldContainerLauncher


def test_osworld_port_resolution_auto_allocates_unique_ports(monkeypatch) -> None:
    launcher = OSWorldContainerLauncher(repo_root=Path.cwd(), emit=None)
    for key in (
        "SNOWL_OSWORLD_SERVER_PORT",
        "SNOWL_OSWORLD_CHROMIUM_PORT",
        "SNOWL_OSWORLD_VNC_PORT",
        "SNOWL_OSWORLD_VLC_PORT",
    ):
        monkeypatch.delenv(key, raising=False)

    # Simulate default ports busy to force allocation to next free values.
    busy = {5000, 9222, 8006, 8080}
    monkeypatch.setattr(launcher, "_is_port_available", lambda p: int(p) not in busy)

    ports, explicit = launcher._resolve_ports()
    assert explicit is False
    assert set(ports.keys()) == {5000, 9222, 8006, 8080}
    assert len(set(ports.values())) == 4
    assert ports[5000] != 5000
    assert ports[9222] != 9222
    assert ports[8006] != 8006
    assert ports[8080] != 8080


def test_osworld_prepare_retries_when_port_conflict(monkeypatch) -> None:
    launcher = OSWorldContainerLauncher(repo_root=Path.cwd(), emit=None)
    vm = Path.cwd() / ".snowl_test_vm_Ubuntu.qcow2"
    vm.write_bytes(b"vm")

    monkeypatch.setenv("SNOWL_OSWORLD_START_RETRIES", "2")
    monkeypatch.setattr(
        launcher,
        "_resolve_boot_inputs",
        lambda: ({}, {str(vm): "/System.qcow2:ro"}, False, {"source": "auto_cached_vm"}),
    )
    monkeypatch.setattr(launcher, "_resolve_cap_add", lambda: ["NET_ADMIN"])
    monkeypatch.setattr(launcher, "_resolve_visual_ready_params", lambda **kwargs: (1.0, 1, 0.5))
    monkeypatch.setattr(
        launcher,
        "_probe_visual_ready",
        lambda **kwargs: (True, {"status_code": 200, "screenshot_bytes": 15000, "attempt": 1, "ready": True}),
    )

    port_batches = iter(
        [
            ({5000: 5000, 9222: 9222, 8006: 8006, 8080: 8080}, False),
            ({5000: 15000, 9222: 19222, 8006: 18006, 8080: 18080}, False),
        ]
    )
    monkeypatch.setattr(launcher, "_resolve_ports", lambda: next(port_batches))

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

    monkeypatch.setattr(osw_container.GuiEnv, "start_container", fake_start_container)
    monkeypatch.setattr(
        osw_container.GuiEnv,
        "container_logs",
        lambda self, **kwargs: {"stdout": "", "stderr": "port is already allocated", "exit_code": 0},
    )
    monkeypatch.setattr(
        osw_container.GuiEnv,
        "stop_container",
        lambda self, **kwargs: {"exit_code": 0},
    )
    monkeypatch.setattr(launcher, "_is_port_conflict", lambda **kwargs: True)

    try:
        out = launcher.prepare(docker_path="docker")
        assert len(calls) == 2
        assert calls[0][5000] == 5000
        assert calls[1][5000] == 15000
        assert out.metadata["ports"][5000] == 15000
    finally:
        if vm.exists():
            vm.unlink()


def test_osworld_visual_ready_params_no_kvm_default(monkeypatch) -> None:
    launcher = OSWorldContainerLauncher(repo_root=Path.cwd(), emit=None)
    monkeypatch.delenv("SNOWL_OSWORLD_VISUAL_READY_TIMEOUT", raising=False)
    monkeypatch.delenv("SNOWL_OSWORLD_VISUAL_READY_MIN_SCREENSHOT_BYTES", raising=False)
    monkeypatch.delenv("SNOWL_OSWORLD_VISUAL_READY_POLL_SEC", raising=False)

    timeout_sec, min_bytes, poll_sec = launcher._resolve_visual_ready_params(
        first_boot=False,
        kvm_disabled=True,
    )
    assert timeout_sec == osw_container.OSWORLD_VISUAL_READY_TIMEOUT_NO_KVM_SEC
    assert min_bytes == osw_container.OSWORLD_VISUAL_READY_MIN_SCREENSHOT_BYTES
    assert poll_sec == osw_container.OSWORLD_VISUAL_READY_POLL_SEC


def test_osworld_probe_visual_ready_succeeds_when_signal_available(monkeypatch) -> None:
    launcher = OSWorldContainerLauncher(repo_root=Path.cwd(), emit=None)

    class _FakeEnv:
        def __init__(self) -> None:
            self._idx = 0

        def observe(self, *, include_accessibility=None, include_terminal=None):  # type: ignore[no-untyped-def]
            self._idx += 1
            if self._idx == 1:
                return {"status_code": 200, "screenshot": b"x" * 2000, "accessibility_tree": "", "terminal_output": ""}
            return {"status_code": 200, "screenshot": b"x" * 12000, "accessibility_tree": "", "terminal_output": ""}

    monkeypatch.setattr(osw_container.time, "sleep", lambda *_args, **_kwargs: None)
    ready, diag = launcher._probe_visual_ready(
        env=_FakeEnv(),  # type: ignore[arg-type]
        timeout_sec=4.0,
        min_screenshot_bytes=10000,
        poll_sec=0.5,
    )
    assert ready is True
    assert int(diag["screenshot_bytes"]) >= 10000
