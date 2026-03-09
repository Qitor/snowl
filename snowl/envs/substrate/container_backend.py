"""Container backend operations used by environment adapters."""

from __future__ import annotations

import os
from typing import Any, Callable, Mapping, Sequence

from snowl.envs.substrate.command_runner import CommandRunner


EventSink = Callable[[dict[str, Any]], None] | None


class ContainerBackend:
    """Docker/Compose helper built on top of CommandRunner."""

    def __init__(self, *, command_runner: CommandRunner) -> None:
        self._runner = command_runner

    def run(
        self,
        *,
        image: str,
        env: Mapping[str, str] | None = None,
        ports: Mapping[int, int] | None = None,
        volumes: Mapping[str, str] | None = None,
        cap_add: Sequence[str] | None = None,
        devices: Sequence[str] | None = None,
        detach: bool = True,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        for cap in (cap_add or ()):
            cap_name = str(cap).strip()
            if cap_name:
                cmd += ["--cap-add", cap_name]
        for device in (devices or ()):
            device_name = str(device).strip()
            if device_name:
                cmd += ["--device", device_name]
        for c_port, h_port in (ports or {}).items():
            cmd += ["-p", f"{h_port}:{c_port}"]
        for host_path, container_path in (volumes or {}).items():
            cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
        for key, value in (env or {}).items():
            cmd += ["-e", f"{key}={value}"]
        cmd.append(str(image))
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            on_event=on_event,
        )

    def rm(
        self,
        container_id: str,
        *,
        force: bool = True,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(str(container_id))
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            on_event=on_event,
        )

    def logs(
        self,
        container_id: str,
        *,
        tail: int = 200,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = ["docker", "logs", "--tail", str(max(1, int(tail))), str(container_id)]
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            on_event=on_event,
        )

    @staticmethod
    def compose_base_cmd(*, project: str, compose_file: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            str(project),
            "-f",
            str(compose_file),
        ]

    def compose_build(
        self,
        *,
        project: str,
        compose_file: str,
        env: Mapping[str, str] | None = None,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = [*self.compose_base_cmd(project=project, compose_file=compose_file), "build"]
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            env=env,
            on_event=on_event,
        )

    def compose_up(
        self,
        *,
        project: str,
        compose_file: str,
        env: Mapping[str, str] | None = None,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = [*self.compose_base_cmd(project=project, compose_file=compose_file), "up", "-d"]
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            env=env,
            on_event=on_event,
        )

    def compose_down(
        self,
        *,
        project: str,
        compose_file: str,
        env: Mapping[str, str] | None = None,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = [*self.compose_base_cmd(project=project, compose_file=compose_file), "down"]
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            env=env,
            on_event=on_event,
        )

    def compose_exec(
        self,
        *,
        project: str,
        compose_file: str,
        service: str,
        command: str,
        env: Mapping[str, str] | None = None,
        on_event: EventSink = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        cmd = [
            *self.compose_base_cmd(project=project, compose_file=compose_file),
            "exec",
            "-T",
            str(service),
            "bash",
            "-lc",
            str(command),
        ]
        return self._runner.run(
            cmd,
            timeout_seconds=timeout_seconds,
            env=env,
            on_event=on_event,
        )
