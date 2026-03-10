"""OSWorld-specific container launcher."""

from __future__ import annotations

import os
import re
import shutil
import socket
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests

from snowl.core import EnvSpec
from snowl.envs import GuiEnv

OSWORLD_DEFAULT_BOOT_URL = (
    "https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip"
)
OSWORLD_DEFAULT_READY_TIMEOUT_SEC = 240.0
OSWORLD_FIRST_BOOT_READY_TIMEOUT_SEC = 1800.0
OSWORLD_DEFAULT_PORT_RETRY_ATTEMPTS = 3
OSWORLD_VISUAL_READY_TIMEOUT_SEC = 120.0
OSWORLD_VISUAL_READY_TIMEOUT_NO_KVM_SEC = 900.0
OSWORLD_VISUAL_READY_TIMEOUT_FIRST_BOOT_SEC = 300.0
OSWORLD_VISUAL_READY_MIN_SCREENSHOT_BYTES = 10_000
OSWORLD_VISUAL_READY_POLL_SEC = 2.0

OSWORLD_CONTAINER_PORTS: tuple[int, ...] = (5000, 9222, 8006, 8080)
OSWORLD_PORT_DEFAULTS: dict[int, int] = {
    5000: 5000,
    9222: 9222,
    8006: 8006,
    8080: 8080,
}
@dataclass
class OSWorldPrepareResult:
    env: GuiEnv
    metadata: dict[str, Any]


class OSWorldContainerLauncher:
    def __init__(
        self,
        *,
        repo_root: Path,
        emit: Callable[[dict[str, Any]], None] | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._emit = emit if callable(emit) else None
        self._settings = dict(settings or {})

    def _setting(self, key: str, default: Any = None) -> Any:
        if key in self._settings:
            return self._settings.get(key)
        return default

    def _emit_event(self, event: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(dict(event))
        except Exception:
            return

    def _osworld_vm_cache_dir(self) -> Path:
        raw = str(self._setting("vm_cache_dir", "")).strip()
        if raw:
            return Path(raw).expanduser().resolve()
        return self._repo_root / "references" / "OSWorld" / "docker_vm_data"

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
                with part.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                        if not chunk:
                            continue
                        fh.write(chunk)
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
        vm_url = str(self._setting("vm_url", OSWORLD_DEFAULT_BOOT_URL)).strip()
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
        if not artifact_path.exists():
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
                members = [x for x in zf.infolist() if x.filename.lower().endswith(".qcow2")]
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

    def _resolve_boot_inputs(self) -> tuple[dict[str, str], dict[str, str], bool, dict[str, Any]]:
        explicit_vm_path = str(self._setting("vm_path", "")).strip()
        explicit_boot_url = str(self._setting("boot", "")).strip()
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
                raise RuntimeError(f"osworld.vm_path not found: {vm_file}")
            volumes[str(vm_file)] = "/System.qcow2:ro"
            boot_config.update({"vm_path_set": True, "source": "env_vm_path", "vm_path": str(vm_file)})
        elif explicit_boot_url:
            container_env["BOOT"] = explicit_boot_url
            first_boot = True
            boot_config.update({"boot_url_set": True, "source": "env_boot_url"})
        else:
            vm_file, downloaded = self._ensure_default_osworld_vm()
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

        for setting_key, mapped in (
            ("disk_size", "DISK_SIZE"),
            ("ram_size", "RAM_SIZE"),
            ("cpu_cores", "CPU_CORES"),
            ("kvm", "KVM"),
        ):
            value = str(self._setting(setting_key, "")).strip()
            if value:
                container_env[mapped] = value

        defaults = {"DISK_SIZE": "32G", "RAM_SIZE": "4G", "CPU_CORES": "4"}
        for key, value in defaults.items():
            container_env.setdefault(key, value)

        return container_env, volumes, first_boot, boot_config

    def _resolve_cap_add(self) -> list[str]:
        raw = str(self._setting("cap_add", "NET_ADMIN")).strip()
        if not raw or raw.lower() in {"0", "false", "off", "none"}:
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

    def _is_port_available(self, port: int) -> bool:
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
            if port not in reserved and self._is_port_available(port):
                return port
            port += 1
        raise RuntimeError(f"No available TCP host port found from {start} to 65535.")

    def _resolve_ports(self) -> tuple[dict[int, int], bool]:
        ports: dict[int, int] = {}
        reserved: set[int] = set()
        has_explicit = False
        for c_port in OSWORLD_CONTAINER_PORTS:
            explicit_ports = self._settings.get("ports")
            raw = ""
            if isinstance(explicit_ports, Mapping):
                raw = str(explicit_ports.get(str(c_port)) or explicit_ports.get(c_port) or "").strip()
            if not raw:
                continue
            has_explicit = True
            host_port = int(raw)
            if host_port < 1 or host_port > 65535:
                raise RuntimeError(f"osworld.ports.{c_port} must be in [1, 65535], got: {host_port}")
            if host_port in reserved:
                raise RuntimeError(f"osworld.ports.{c_port} duplicates another OSWorld host port: {host_port}")
            if not self._is_port_available(host_port):
                raise RuntimeError(f"osworld.ports.{c_port}={host_port} is already in use on localhost.")
            ports[c_port] = host_port
            reserved.add(host_port)
        for c_port in OSWORLD_CONTAINER_PORTS:
            if c_port in ports:
                continue
            host_port = self._find_available_port(start=OSWORLD_PORT_DEFAULTS[c_port], reserved=reserved)
            ports[c_port] = host_port
            reserved.add(host_port)
        return ports, has_explicit

    def _resolve_visual_ready_params(
        self,
        *,
        first_boot: bool,
        kvm_disabled: bool,
    ) -> tuple[float, int, float]:
        timeout_raw = str(self._setting("visual_ready_timeout", "")).strip()
        min_bytes_raw = str(self._setting("visual_ready_min_screenshot_bytes", "")).strip()
        poll_raw = str(self._setting("visual_ready_poll_sec", "")).strip()

        if timeout_raw:
            timeout_sec = max(1.0, float(timeout_raw))
        elif kvm_disabled:
            timeout_sec = OSWORLD_VISUAL_READY_TIMEOUT_NO_KVM_SEC
        elif first_boot:
            timeout_sec = OSWORLD_VISUAL_READY_TIMEOUT_FIRST_BOOT_SEC
        else:
            timeout_sec = OSWORLD_VISUAL_READY_TIMEOUT_SEC

        if min_bytes_raw:
            min_screenshot_bytes = max(1, int(min_bytes_raw))
        else:
            min_screenshot_bytes = OSWORLD_VISUAL_READY_MIN_SCREENSHOT_BYTES

        if poll_raw:
            poll_sec = max(0.5, float(poll_raw))
        else:
            poll_sec = OSWORLD_VISUAL_READY_POLL_SEC
        return timeout_sec, min_screenshot_bytes, poll_sec

    def _probe_visual_ready(
        self,
        *,
        env: GuiEnv,
        timeout_sec: float,
        min_screenshot_bytes: int,
        poll_sec: float,
    ) -> tuple[bool, dict[str, Any]]:
        deadline = time.time() + max(1.0, float(timeout_sec))
        attempt = 0
        last_diag: dict[str, Any] = {
            "status_code": None,
            "screenshot_bytes": 0,
            "accessibility_chars": 0,
            "terminal_chars": 0,
        }
        while time.time() < deadline:
            attempt += 1
            obs = env.observe(include_accessibility=True, include_terminal=True)
            screenshot_bytes = len(obs.get("screenshot") or b"")
            accessibility_chars = len(str(obs.get("accessibility_tree") or ""))
            terminal_chars = len(str(obs.get("terminal_output") or ""))
            status_code = obs.get("status_code")
            ready = bool(
                int(status_code or 0) == 200
                and (
                    screenshot_bytes >= int(min_screenshot_bytes)
                    or accessibility_chars > 0
                    or terminal_chars > 0
                )
            )
            last_diag = {
                "status_code": status_code,
                "screenshot_bytes": screenshot_bytes,
                "accessibility_chars": accessibility_chars,
                "terminal_chars": terminal_chars,
                "attempt": attempt,
                "ready": ready,
            }
            self._emit_event(
                {
                    "event": "osworld.container.visual_probe",
                    "phase": "env",
                    **last_diag,
                    "min_screenshot_bytes": int(min_screenshot_bytes),
                }
            )
            if ready:
                return True, last_diag
            time.sleep(max(0.5, float(poll_sec)))
        return False, last_diag

    @staticmethod
    def _extract_container_id(text: str) -> str | None:
        first = str(text or "").strip().splitlines()
        if not first:
            return None
        token = first[0].strip()
        if re.fullmatch(r"[0-9a-f]{12,64}", token):
            return token
        return None

    @staticmethod
    def _is_port_conflict(*, start_evt: Mapping[str, Any], logs_text: str) -> bool:
        stderr_text = str(start_evt.get("stderr") or "")
        combined = (stderr_text + "\n" + str(logs_text or "")).lower()
        return "port is already allocated" in combined

    def prepare(self, *, docker_path: str) -> OSWorldPrepareResult:
        del docker_path
        container_env, volumes, first_boot, boot_config = self._resolve_boot_inputs()
        cap_add = self._resolve_cap_add()
        ports, ports_explicit = self._resolve_ports()
        host_kvm_exists = bool(os.path.exists("/dev/kvm"))
        kvm_disabled = bool(
            str(container_env.get("KVM", "")).strip().upper() == "N"
            or not host_kvm_exists
        )

        start_retry_raw = str(self._setting("start_retries", "")).strip()
        if start_retry_raw:
            start_retries = max(1, int(start_retry_raw))
        else:
            start_retries = OSWORLD_DEFAULT_PORT_RETRY_ATTEMPTS

        timeout_raw = str(self._setting("ready_timeout", "")).strip()
        if timeout_raw:
            ready_timeout_sec = max(1.0, float(timeout_raw))
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

        image = str(self._setting("image", "happysixd/osworld-docker"))
        self._emit_event(
            {
                "event": "osworld.container.config",
                "phase": "env",
                "image": image,
                "ready_timeout_sec": ready_timeout_sec,
                "boot_config": boot_config,
                "cap_add": cap_add,
                "ports": ports,
                "ports_explicit": ports_explicit,
                "start_retries": start_retries,
            }
        )

        for attempt in range(1, start_retries + 1):
            self._emit_event({"event": "osworld.container.starting", "phase": "env", "attempt": attempt, "ports": ports})
            start_evt = env.start_container(
                image=image,
                env=container_env,
                ports=ports,
                volumes=volumes,
                cap_add=cap_add,
                on_event=lambda evt: self._emit_event({"phase": "env", **dict(evt)}),
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
                visual_timeout_sec, min_screenshot_bytes, visual_poll_sec = self._resolve_visual_ready_params(
                    first_boot=first_boot,
                    kvm_disabled=kvm_disabled,
                )
                visual_ready, visual_diag = self._probe_visual_ready(
                    env=env,
                    timeout_sec=visual_timeout_sec,
                    min_screenshot_bytes=min_screenshot_bytes,
                    poll_sec=visual_poll_sec,
                )
                if visual_ready:
                    self._emit_event(
                        {
                            "event": "osworld.container.visual_ready",
                            "phase": "env",
                            **visual_diag,
                            "timeout_sec": visual_timeout_sec,
                        }
                    )
                    return OSWorldPrepareResult(
                        env=env,
                        metadata={"image": image, "ports": ports},
                    )
                logs_out = env.container_logs(
                    tail=120,
                    on_event=lambda evt: self._emit_event({"phase": "env", **dict(evt)}),
                )
                logs_stdout = str(logs_out.get("stdout") or "").strip()
                logs_stderr = str(logs_out.get("stderr") or "").strip()
                logs_text = "\n".join(x for x in (logs_stdout, logs_stderr) if x).strip()
                no_kvm_hint = (
                    " Host has no KVM acceleration; OS boot may take much longer before GUI becomes usable. "
                    "Increase osworld.visual_ready_timeout if needed."
                    if kvm_disabled
                    else ""
                )
                try:
                    env.stop_container(on_event=lambda evt: self._emit_event({"phase": "env", **dict(evt)}))
                except Exception:
                    pass
                raise RuntimeError(
                    "osworld container responded on /screenshot but desktop is not visually ready. "
                    f"last_probe={visual_diag}. {logs_text}{no_kvm_hint}"
                )

            container_id_candidate = self._extract_container_id(str(start_evt.get("stdout") or ""))
            if container_id_candidate and not env.container_id:
                env.container_id = container_id_candidate

            logs_out = env.container_logs(
                tail=120,
                on_event=lambda evt: self._emit_event({"phase": "env", **dict(evt)}),
            )
            logs_stdout = str(logs_out.get("stdout") or "").strip()
            logs_stderr = str(logs_out.get("stderr") or "").strip()
            logs_text = "\n".join(x for x in (logs_stdout, logs_stderr) if x).strip()
            lower_logs = logs_text.lower()

            hint = ""
            if "no boot disk specified" in lower_logs:
                hint = (
                    " OSWorld VM boot disk is missing. Configure BOOT in the container runtime "
                    "or provide a valid OSWorld VM disk (qcow2) mapping."
                )
            if "downloading" in lower_logs and "qcow2" in lower_logs:
                hint += (
                    " OSWorld is downloading the VM image on first boot; increase "
                    "osworld.ready_timeout (e.g. 1800 seconds) and retry."
                )
            if self._is_port_conflict(start_evt=start_evt, logs_text=logs_text):
                hint += (
                    " Host port conflict detected. Re-run with --max-trials 1, or let Snowl auto-assign "
                    "ports by not pinning osworld.ports in project.yml."
                )

            try:
                env.stop_container(on_event=lambda evt: self._emit_event({"phase": "env", **dict(evt)}))
            except Exception:
                pass

            can_retry = (
                attempt < start_retries
                and (not ports_explicit)
                and self._is_port_conflict(start_evt=start_evt, logs_text=logs_text)
            )
            if can_retry:
                old_ports = dict(ports)
                ports, _ = self._resolve_ports()
                self._emit_event(
                    {
                        "event": "osworld.container.retry",
                        "phase": "env",
                        "attempt": attempt,
                        "reason": "port_conflict",
                        "ports_prev": old_ports,
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
