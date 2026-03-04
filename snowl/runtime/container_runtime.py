"""Common container runtime orchestration for benchmark agents."""

from __future__ import annotations

import os
import re
import socket
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests
from snowl.core import EnvSpec
from snowl.envs import GuiEnv, TerminalEnv

OSWORLD_DEFAULT_BOOT_URL = (
    "https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip"
)
OSWORLD_DEFAULT_READY_TIMEOUT_SEC = 240.0
OSWORLD_FIRST_BOOT_READY_TIMEOUT_SEC = 1800.0
OSWORLD_DEFAULT_PORT_RETRY_ATTEMPTS = 3

OSWORLD_CONTAINER_PORTS: tuple[int, ...] = (5000, 9222, 8006, 8080)
OSWORLD_PORT_DEFAULTS: dict[int, int] = {
    5000: 5000,
    9222: 9222,
    8006: 8006,
    8080: 8080,
}
OSWORLD_PORT_ENV: dict[int, str] = {
    5000: "SNOWL_OSWORLD_SERVER_PORT",
    9222: "SNOWL_OSWORLD_CHROMIUM_PORT",
    8006: "SNOWL_OSWORLD_VNC_PORT",
    8080: "SNOWL_OSWORLD_VLC_PORT",
}


@dataclass
class ContainerSession:
    kind: str
    env: Any
    benchmark: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ContainerRuntime:
    def __init__(
        self,
        *,
        task_id: str,
        agent_id: str,
        variant_id: str,
        task_env_type: str,
        task_metadata: Mapping[str, Any],
        sample: Mapping[str, Any],
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.task_id = task_id
        self.agent_id = agent_id
        self.variant_id = variant_id
        self.task_env_type = task_env_type
        self.task_metadata = dict(task_metadata or {})
        self.sample = dict(sample or {})
        self._emit = emit if callable(emit) else None
        self._session: ContainerSession | None = None

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._emit is None:
            return
        payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "variant_id": self.variant_id,
            **dict(event),
        }
        try:
            self._emit(payload)
        except Exception:
            return

    def _emit_env_stream(self, event: dict[str, Any], *, project: str | None = None, compose_file: str | None = None) -> None:
        payload = dict(event)
        payload.setdefault("phase", "env")
        if project:
            payload.setdefault("project", project)
        if compose_file:
            payload.setdefault("compose_file", compose_file)
        self._emit_event(payload)

    def _ensure_docker_available(self, *, benchmark: str) -> str:
        docker_path = shutil.which("docker")
        if docker_path:
            return docker_path
        msg = (
            "docker executable not found in PATH. Install/start Docker Desktop and ensure "
            "'docker' is available in the current shell before running "
            f"{benchmark}."
        )
        self._emit_event(
            {
                "event": "runtime.env.preflight.error",
                "phase": "env",
                "code": "docker_not_found",
                "benchmark": benchmark,
                "message": msg,
            }
        )
        raise RuntimeError(msg)

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _osworld_vm_cache_dir(self) -> Path:
        raw = str(os.getenv("SNOWL_OSWORLD_VM_CACHE_DIR", "")).strip()
        if raw:
            return Path(raw).expanduser().resolve()
        return self._repo_root() / "references" / "OSWorld" / "docker_vm_data"

    def _vm_name_from_url(self, url: str) -> str:
        name = Path(urlparse(url).path).name or "Ubuntu.qcow2.zip"
        if name.endswith(".zip"):
            name = name[:-4]
        if not name.lower().endswith(".qcow2"):
            name = f"{name}.qcow2"
        return name

    def _download_to_file(self, *, url: str, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_suffix(dst.suffix + ".part")
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        self._emit_event(
            {
                "event": "runtime.env.preflight.download.start",
                "phase": "env",
                "url": url,
                "target": str(dst),
            }
        )
        downloaded = 0
        emit_every = 256 * 1024 * 1024
        next_emit = emit_every
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0) or 0)
                with part.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded >= next_emit:
                            payload = {
                                "event": "runtime.env.preflight.download.progress",
                                "phase": "env",
                                "url": url,
                                "downloaded_bytes": downloaded,
                            }
                            if total > 0:
                                payload["total_bytes"] = total
                                payload["percent"] = round(downloaded * 100.0 / total, 2)
                            self._emit_event(payload)
                            next_emit += emit_every
            part.replace(dst)
        except Exception:
            try:
                if part.exists():
                    part.unlink()
            except Exception:
                pass
            raise
        self._emit_event(
            {
                "event": "runtime.env.preflight.download.finish",
                "phase": "env",
                "url": url,
                "target": str(dst),
                "downloaded_bytes": downloaded,
            }
        )

    def _ensure_default_osworld_vm(self) -> tuple[Path, bool]:
        cache_dir = self._osworld_vm_cache_dir()
        vm_url = str(os.getenv("SNOWL_OSWORLD_VM_URL", OSWORLD_DEFAULT_BOOT_URL)).strip()
        vm_name = self._vm_name_from_url(vm_url)
        vm_path = cache_dir / vm_name
        if vm_path.exists():
            self._emit_event(
                {
                    "event": "runtime.env.preflight.cache.hit",
                    "phase": "env",
                    "path": str(vm_path),
                }
            )
            return vm_path, False

        artifact_name = Path(urlparse(vm_url).path).name or f"{vm_name}.zip"
        artifact_path = cache_dir / artifact_name
        needs_download = not artifact_path.exists()
        if needs_download:
            self._download_to_file(url=vm_url, dst=artifact_path)

        if artifact_path.suffix.lower() == ".zip":
            self._emit_event(
                {
                    "event": "runtime.env.preflight.extract.start",
                    "phase": "env",
                    "archive": str(artifact_path),
                    "target": str(vm_path),
                }
            )
            part = vm_path.with_suffix(vm_path.suffix + ".part")
            if part.exists():
                try:
                    part.unlink()
                except Exception:
                    pass
            with zipfile.ZipFile(artifact_path, "r") as zf:
                members = [i for i in zf.infolist() if i.filename.lower().endswith(".qcow2")]
                if not members:
                    raise RuntimeError(f"No qcow2 image found in archive: {artifact_path}")
                member = members[0]
                with zf.open(member, "r") as src, part.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)
            part.replace(vm_path)
            self._emit_event(
                {
                    "event": "runtime.env.preflight.extract.finish",
                    "phase": "env",
                    "archive": str(artifact_path),
                    "target": str(vm_path),
                }
            )
        else:
            artifact_path.replace(vm_path)

        return vm_path, True

    def _resolve_osworld_boot_inputs(self) -> tuple[dict[str, str], dict[str, str], bool, dict[str, Any]]:
        explicit_vm_path = str(os.getenv("SNOWL_OSWORLD_VM_PATH", "")).strip()
        explicit_boot_url = str(os.getenv("SNOWL_OSWORLD_BOOT", "")).strip()
        container_env: dict[str, str] = {}
        volumes: dict[str, str] = {}
        boot_config: dict[str, Any] = {
            "boot_url_set": False,
            "vm_path_set": False,
            "source": "auto",
            "downloaded": False,
        }
        first_boot = False

        if explicit_vm_path:
            vm_file = Path(explicit_vm_path).expanduser().resolve()
            if not vm_file.exists():
                raise RuntimeError(f"SNOWL_OSWORLD_VM_PATH not found: {vm_file}")
            volumes[str(vm_file)] = "/System.qcow2:ro"
            boot_config.update(
                {
                    "vm_path_set": True,
                    "source": "env_vm_path",
                    "vm_path": str(vm_file),
                }
            )
        elif explicit_boot_url:
            container_env["BOOT"] = explicit_boot_url
            first_boot = True
            boot_config.update(
                {
                    "boot_url_set": True,
                    "source": "env_boot_url",
                }
            )
        else:
            try:
                vm_file, downloaded = self._ensure_default_osworld_vm()
            except Exception as exc:
                raise RuntimeError(
                    "Failed to prepare local OSWorld VM image. "
                    "You can also provide SNOWL_OSWORLD_VM_PATH to an existing qcow2 file. "
                    f"detail={exc}"
                ) from exc
            volumes[str(vm_file)] = "/System.qcow2:ro"
            first_boot = bool(downloaded)
            boot_config.update(
                {
                    "vm_path_set": True,
                    "source": "auto_cached_vm",
                    "vm_path": str(vm_file),
                    "downloaded": bool(downloaded),
                }
            )

        for key in ("SNOWL_OSWORLD_DISK_SIZE", "SNOWL_OSWORLD_RAM_SIZE", "SNOWL_OSWORLD_CPU_CORES", "SNOWL_OSWORLD_KVM"):
            value = str(os.getenv(key, "")).strip()
            if value:
                mapped = {
                    "SNOWL_OSWORLD_DISK_SIZE": "DISK_SIZE",
                    "SNOWL_OSWORLD_RAM_SIZE": "RAM_SIZE",
                    "SNOWL_OSWORLD_CPU_CORES": "CPU_CORES",
                    "SNOWL_OSWORLD_KVM": "KVM",
                }[key]
                container_env[mapped] = value

        return container_env, volumes, first_boot, boot_config

    def _resolve_osworld_cap_add(self) -> list[str]:
        raw = str(os.getenv("SNOWL_OSWORLD_CAP_ADD", "NET_ADMIN")).strip()
        if not raw:
            return []
        if raw.lower() in {"0", "false", "off", "none"}:
            return []
        caps: list[str] = []
        seen: set[str] = set()
        for token in re.split(r"[,\s]+", raw):
            cap = token.strip()
            if not cap:
                continue
            key = cap.upper()
            if key in seen:
                continue
            seen.add(key)
            caps.append(cap)
        return caps

    def _is_tcp_port_available(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", int(port)))
            return True
        except OSError:
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _find_available_port(self, *, start: int, reserved: set[int]) -> int:
        port = max(1, int(start))
        while port <= 65535:
            if port not in reserved and self._is_tcp_port_available(port):
                return port
            port += 1
        raise RuntimeError(f"No available TCP host port found from {start} to 65535.")

    def _resolve_osworld_ports(self) -> tuple[dict[int, int], bool]:
        ports: dict[int, int] = {}
        reserved: set[int] = set()
        has_explicit = False

        for c_port in OSWORLD_CONTAINER_PORTS:
            env_key = OSWORLD_PORT_ENV[c_port]
            raw = str(os.getenv(env_key, "")).strip()
            if not raw:
                continue
            has_explicit = True
            try:
                h_port = int(raw)
            except Exception as exc:
                raise RuntimeError(f"{env_key} must be an integer, got: {raw}") from exc
            if h_port < 1 or h_port > 65535:
                raise RuntimeError(f"{env_key} must be in [1, 65535], got: {h_port}")
            if h_port in reserved:
                raise RuntimeError(f"{env_key} duplicates another OSWorld host port: {h_port}")
            if not self._is_tcp_port_available(h_port):
                raise RuntimeError(f"{env_key}={h_port} is already in use on localhost.")
            ports[c_port] = h_port
            reserved.add(h_port)

        for c_port in OSWORLD_CONTAINER_PORTS:
            if c_port in ports:
                continue
            start = OSWORLD_PORT_DEFAULTS[c_port]
            h_port = self._find_available_port(start=start, reserved=reserved)
            ports[c_port] = h_port
            reserved.add(h_port)

        return ports, has_explicit

    def _extract_container_id(self, text: str) -> str | None:
        first = str(text or "").strip().splitlines()
        if not first:
            return None
        token = first[0].strip()
        if re.fullmatch(r"[0-9a-f]{12,64}", token):
            return token
        return None

    def _is_osworld_port_conflict(self, *, start_evt: Mapping[str, Any], logs_text: str) -> bool:
        stderr_text = str(start_evt.get("stderr") or "")
        combined = (stderr_text + "\n" + str(logs_text or "")).lower()
        return "port is already allocated" in combined

    def prepare(self) -> ContainerSession | None:
        benchmark = str(self.task_metadata.get("benchmark") or "").strip().lower()
        if benchmark == "terminalbench":
            self._session = self._prepare_terminalbench()
            return self._session
        if benchmark == "osworld":
            self._session = self._prepare_osworld()
            return self._session
        return None

    def close(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        session = self._session
        self._session = None
        env = session.env
        if session.kind == "terminal_compose":
            project = getattr(env, "compose_project", None)
            self._emit_event({"event": "terminalbench.container.stopping", "phase": "env", "project": project})
            down_out = env.compose_down(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=project,
                    compose_file=getattr(env, "compose_file", None),
                )
            )
            payload = {"event": "terminalbench.container.stopped", "phase": "env", "project": project}
            payload.update(
                {
                    "exit_code": down_out.get("exit_code"),
                    "duration_ms": down_out.get("duration_ms"),
                    "command_text": " ".join(down_out.get("command", [])) if isinstance(down_out.get("command"), list) else down_out.get("command"),
                    "stdout_tail": str(down_out.get("stdout", ""))[-240:],
                    "stderr_tail": str(down_out.get("stderr", ""))[-240:],
                }
            )
            self._emit_event(payload)
            return down_out
        if session.kind == "gui_container":
            self._emit_event({"event": "osworld.container.stopping", "phase": "env"})
            stop_evt = env.stop_container(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=None,
                    compose_file=None,
                )
            )
            self._emit_event(
                {
                    "event": "osworld.container.stopped",
                    "phase": "env",
                    "exit_code": stop_evt.get("exit_code"),
                }
            )
            return stop_evt
        return None

    def _prepare_terminalbench(self) -> ContainerSession:
        sample_meta = dict(self.sample.get("metadata", {}) or {})
        task_id = str(sample_meta.get("task_id") or "task")
        sample_id = str(self.sample.get("id") or "sample")
        safe_task = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-") or "task"
        safe_sample = re.sub(r"[^a-zA-Z0-9._-]+", "-", sample_id).strip("-") or "sample"
        trial_name = f"snowl-tb-{safe_task}-{safe_sample[:16]}"
        workdir = sample_meta.get("task_root") or str(Path.cwd())
        workdir_path = Path(str(workdir)).resolve()
        logs_root = workdir_path / ".snowl_logs" / safe_sample
        agent_logs_root = workdir_path / ".snowl_agent_logs" / safe_sample
        logs_root.mkdir(parents=True, exist_ok=True)
        agent_logs_root.mkdir(parents=True, exist_ok=True)
        docker_compose_path = str(sample_meta.get("docker_compose_path") or "").strip()
        use_compose = bool(docker_compose_path and Path(docker_compose_path).exists())
        compose_build = os.getenv("SNOWL_TB_COMPOSE_BUILD", "1") == "1"
        compose_env = {
            "T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME": trial_name,
            "T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME": f"tb__{safe_task}__client",
            "T_BENCH_TASK_DOCKER_NAME_PREFIX": f"tb__{safe_task}",
            "T_BENCH_CONTAINER_LOGS_PATH": "/var/log/tbench",
            "T_BENCH_CONTAINER_AGENT_LOGS_PATH": "/agent-logs",
            "T_BENCH_TEST_DIR": "/tests",
            "T_BENCH_TASK_LOGS_PATH": str(logs_root),
            "T_BENCH_TASK_AGENT_LOGS_PATH": str(agent_logs_root),
            "TEST_DIR": "/tests",
        }
        env = TerminalEnv(
            env_spec=EnvSpec(
                env_type="terminal",
                provided_ops=(
                    "process.run",
                    "terminal.exec",
                    "terminal.send_keys",
                    "terminal.capture",
                    "terminal.wait",
                ),
            ),
            workdir=str(workdir_path),
            compose_file=(docker_compose_path if docker_compose_path else None),
            use_docker_compose=use_compose,
            compose_build=compose_build,
            compose_project=trial_name,
            compose_service=str(sample_meta.get("compose_service", "client")),
            compose_env=compose_env,
        )
        if env.use_docker_compose:
            docker_path = self._ensure_docker_available(benchmark="terminalbench")
            self._emit_event(
                {
                    "event": "terminalbench.container.config",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                    "service": env.compose_service,
                    "docker_path": docker_path,
                    "compose_build": env.compose_build,
                    "env_injected": {
                        "client_container": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_CONTAINER_NAME"),
                        "client_image": env.compose_env.get("T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME"),
                        "test_dir": env.compose_env.get("T_BENCH_TEST_DIR"),
                        "task_logs": env.compose_env.get("T_BENCH_TASK_LOGS_PATH"),
                        "agent_logs": env.compose_env.get("T_BENCH_TASK_AGENT_LOGS_PATH"),
                    },
                }
            )
            self._emit_event(
                {
                    "event": "terminalbench.container.starting",
                    "phase": "env",
                    "compose_file": env.compose_file,
                    "project": env.compose_project,
                }
            )
            up_out = env.compose_up(
                on_event=lambda evt: self._emit_env_stream(
                    evt,
                    project=env.compose_project,
                    compose_file=env.compose_file,
                )
            )
            build_out = up_out.get("build")
            if isinstance(build_out, Mapping):
                self._emit_event(
                    {
                        "event": "terminalbench.container.build",
                        "phase": "env",
                        "project": env.compose_project,
                        "exit_code": build_out.get("exit_code"),
                        "duration_ms": build_out.get("duration_ms"),
                        "command_text": " ".join(build_out.get("command", []))
                        if isinstance(build_out.get("command"), list)
                        else build_out.get("command"),
                        "stdout_tail": str(build_out.get("stdout", ""))[-240:],
                        "stderr_tail": str(build_out.get("stderr", ""))[-240:],
                    }
                )
            self._emit_event(
                {
                    "event": "terminalbench.container.started",
                    "phase": "env",
                    "project": env.compose_project,
                    "exit_code": up_out.get("exit_code"),
                    "duration_ms": up_out.get("duration_ms"),
                    "command_text": " ".join(up_out.get("command", []))
                    if isinstance(up_out.get("command"), list)
                    else up_out.get("command"),
                    "stdout_tail": str(up_out.get("stdout", ""))[-240:],
                    "stderr_tail": str(up_out.get("stderr", ""))[-240:],
                }
            )
            if up_out.get("exit_code", 1) != 0:
                raise RuntimeError(
                    "terminalbench docker compose up failed: "
                    + str((up_out.get("stderr") or up_out.get("stdout") or "").strip())
                )
        else:
            self._emit_event(
                {
                    "event": "terminalbench.container.disabled",
                    "phase": "env",
                    "reason": "compose_file_not_found",
                    "docker_compose_path": docker_compose_path,
                }
            )
        return ContainerSession(kind="terminal_compose", env=env, benchmark="terminalbench", metadata={"project": env.compose_project})

    def _prepare_osworld(self) -> ContainerSession:
        docker_path = self._ensure_docker_available(benchmark="osworld")
        container_env, volumes, first_boot, boot_config = self._resolve_osworld_boot_inputs()
        cap_add = self._resolve_osworld_cap_add()
        ports, ports_explicit = self._resolve_osworld_ports()
        start_retry_raw = str(os.getenv("SNOWL_OSWORLD_START_RETRIES", "")).strip()
        if start_retry_raw:
            try:
                start_retries = max(1, int(start_retry_raw))
            except Exception:
                start_retries = OSWORLD_DEFAULT_PORT_RETRY_ATTEMPTS
        else:
            start_retries = OSWORLD_DEFAULT_PORT_RETRY_ATTEMPTS
        timeout_raw = str(os.getenv("SNOWL_OSWORLD_READY_TIMEOUT", "")).strip()
        if timeout_raw:
            try:
                ready_timeout_sec = max(1.0, float(timeout_raw))
            except Exception:
                ready_timeout_sec = OSWORLD_DEFAULT_READY_TIMEOUT_SEC
        else:
            ready_timeout_sec = (
                OSWORLD_FIRST_BOOT_READY_TIMEOUT_SEC
                if first_boot
                else OSWORLD_DEFAULT_READY_TIMEOUT_SEC
            )
        env = GuiEnv(
            env_spec=EnvSpec(
                env_type="gui",
                provided_ops=(
                    "gui.action",
                    "gui.click",
                    "gui.type",
                    "gui.key",
                    "gui.scroll",
                    "gui.observe",
                    "gui.wait",
                    "gui.terminate",
                ),
            ),
            config={"ready_timeout_sec": ready_timeout_sec},
        )
        image = os.getenv("SNOWL_OSWORLD_IMAGE", "happysixd/osworld-docker")
        self._emit_event(
            {
                "event": "osworld.container.config",
                "phase": "env",
                "image": image,
                "docker_path": docker_path,
                "ready_timeout_sec": ready_timeout_sec,
                "boot_config": boot_config,
                "cap_add": cap_add,
                "ports": ports,
                "ports_explicit": ports_explicit,
                "start_retries": start_retries,
            }
        )
        for attempt in range(1, start_retries + 1):
            self._emit_event(
                {
                    "event": "osworld.container.starting",
                    "phase": "env",
                    "attempt": attempt,
                    "ports": ports,
                }
            )
            start_evt = env.start_container(
                image=image,
                env=container_env,
                ports=ports,
                volumes=volumes,
                cap_add=cap_add,
                on_event=lambda evt: self._emit_env_stream(evt),
            )
            exit_code_raw = start_evt.get("exit_code")
            try:
                exit_code = int(exit_code_raw) if exit_code_raw is not None else 1
            except Exception:
                exit_code = 1
            ready = bool(start_evt.get("ready"))
            self._emit_event(
                {
                    "event": "osworld.container.started",
                    "phase": "env",
                    "attempt": attempt,
                    "exit_code": exit_code,
                    "ready": ready,
                    "ports": ports,
                }
            )
            if exit_code == 0 and ready:
                return ContainerSession(kind="gui_container", env=env, benchmark="osworld", metadata={"image": image, "ports": ports})

            container_id_candidate = self._extract_container_id(str(start_evt.get("stdout") or ""))
            if container_id_candidate and not env.container_id:
                env.container_id = container_id_candidate

            logs_out = env.container_logs(
                tail=120,
                on_event=lambda evt: self._emit_env_stream(evt),
            )
            logs_stdout = str(logs_out.get("stdout") or "").strip()
            logs_stderr = str(logs_out.get("stderr") or "").strip()
            logs_text = "\n".join(part for part in (logs_stdout, logs_stderr) if part).strip()
            lower_logs = logs_text.lower()
            if "no boot disk specified" in lower_logs:
                hint = (
                    " OSWorld VM boot disk is missing. Configure BOOT in the container runtime "
                    "or provide a valid OSWorld VM disk (qcow2) mapping."
                )
            else:
                hint = ""
            if "downloading" in lower_logs and "qcow2" in lower_logs:
                hint += (
                    " OSWorld is downloading the VM image on first boot; increase "
                    "SNOWL_OSWORLD_READY_TIMEOUT (e.g. 1800 seconds) and retry."
                )
            if self._is_osworld_port_conflict(start_evt=start_evt, logs_text=logs_text):
                hint += (
                    " Host port conflict detected. Re-run with --max-trials 1, or let Snowl auto-assign "
                    "ports by not pinning SNOWL_OSWORLD_*_PORT env vars."
                )
            try:
                env.stop_container(
                    on_event=lambda evt: self._emit_env_stream(evt),
                )
            except Exception:
                pass

            can_retry_port_conflict = (
                attempt < start_retries
                and (not ports_explicit)
                and self._is_osworld_port_conflict(start_evt=start_evt, logs_text=logs_text)
            )
            if can_retry_port_conflict:
                previous_ports = dict(ports)
                ports, _ = self._resolve_osworld_ports()
                self._emit_event(
                    {
                        "event": "osworld.container.retry",
                        "phase": "env",
                        "attempt": attempt,
                        "reason": "port_conflict",
                        "ports_prev": previous_ports,
                        "ports_next": ports,
                    }
                )
                continue

            if exit_code != 0:
                raise RuntimeError(
                    "osworld container start failed with non-zero exit_code="
                    + str(exit_code)
                    + ". "
                    + (logs_text or str(start_evt.get("stderr") or "unknown startup failure"))
                    + hint
                )
            raise RuntimeError(
                "osworld container did not become ready within timeout. "
                + (logs_text or "No container logs captured.")
                + hint
            )

        raise RuntimeError("osworld container start failed after retries.")
