"""GUI environment contract with optional Docker-backed runtime."""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import requests

from snowl.core import EnvSpec, validate_env_spec

_OSWORLD_FUNC_CACHE: dict[tuple[str, str], Callable[..., Any]] = {}


@dataclass
class _OSWorldEvalContext:
    controller: Any
    vm_ip: str
    server_port: int
    cache_dir: str
    evaluator: Mapping[str, Any]
    action_history: list[Any]
    enable_proxy: bool = False

    @property
    def vm_platform(self) -> Any:
        try:
            return self.controller.get_vm_platform()
        except Exception:
            return None

    @property
    def vm_screen_size(self) -> Any:
        try:
            return self.controller.get_vm_screen_size()
        except Exception:
            return None


@dataclass
class GuiEnv:
    env_spec: EnvSpec
    config: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    container_id: str | None = None
    controller_endpoint: str | None = None
    server_port: int | None = None
    chromium_port: int | None = None
    vnc_port: int | None = None
    vlc_port: int | None = None
    _last_observation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_env_spec(self.env_spec)

    @property
    def env_id(self) -> str:
        return f"{self.env_spec.env_type}:gui"

    @property
    def provided_ops(self) -> tuple[str, ...]:
        return self.env_spec.provided_ops

    def reset(self) -> dict[str, Any]:
        self.history.clear()
        self._last_observation = {}
        return {"status": "reset"}

    def close(self) -> None:
        if self.container_id:
            self.stop_container()
        self.history.clear()

    def start_container(
        self,
        *,
        image: str | None = None,
        env: Mapping[str, str] | None = None,
        ports: Mapping[int, int] | None = None,
        volumes: Mapping[str, str] | None = None,
        cap_add: Sequence[str] | None = None,
        detach: bool = True,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        image = image or (self.env_spec.sandbox_spec.image if self.env_spec.sandbox_spec else None) or "happysixd/osworld-docker"
        if ports is None:
            ports = {
                5000: int(self.config.get("server_port", 5000)),
                9222: int(self.config.get("chromium_port", 9222)),
                8006: int(self.config.get("vnc_port", 8006)),
                8080: int(self.config.get("vlc_port", 8080)),
            }
        # KVM device detection and env patch
        env_dict = dict(env or {})
        kvm_device = "/dev/kvm"
        kvm_exists = os.path.exists(kvm_device)
        if kvm_exists:
            # Add --device /dev/kvm to docker run
            kvm_flag = True
        else:
            env_dict["KVM"] = "N"
            kvm_flag = False
        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        for cap in (cap_add or ()):
            cap_name = str(cap).strip()
            if cap_name:
                cmd += ["--cap-add", cap_name]
        if kvm_flag:
            cmd += ["--device", kvm_device]
        for c_port, h_port in (ports or {}).items():
            cmd += ["-p", f"{h_port}:{c_port}"]
        for host_path, container_path in (volumes or {}).items():
            cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
        for k, v in env_dict.items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(image)
        command_text = " ".join(cmd)
        if callable(on_event):
            try:
                on_event({"event": "runtime.env.command.start", "command_text": command_text})
            except Exception:
                pass
        started = int(time.time() * 1000)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ended = int(time.time() * 1000)
        out = {
            "event": "gui.container.start",
            "command": cmd,
            "exit_code": int(proc.returncode),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "started_at_ms": started,
            "ended_at_ms": ended,
            "duration_ms": max(0, ended - started),
        }
        if callable(on_event):
            stdout_text = (proc.stdout or "").strip()
            stderr_text = (proc.stderr or "").strip()
            try:
                if stdout_text:
                    on_event({"event": "runtime.env.command.stdout", "command_text": command_text, "chunk": stdout_text})
                if stderr_text:
                    on_event({"event": "runtime.env.command.stderr", "command_text": command_text, "chunk": stderr_text})
                on_event(
                    {
                        "event": "runtime.env.command.finish",
                        "command_text": command_text,
                        "exit_code": int(proc.returncode),
                        "duration_ms": max(0, ended - started),
                    }
                )
            except Exception:
                pass
        if proc.returncode == 0:
            self.container_id = (proc.stdout or "").strip().splitlines()[0][:64]
            out["container_id"] = self.container_id
            # Keep exposed host ports for controller requests.
            self.server_port = int((ports or {}).get(5000, 5000))
            self.chromium_port = int((ports or {}).get(9222, 9222))
            self.vnc_port = int((ports or {}).get(8006, 8006))
            self.vlc_port = int((ports or {}).get(8080, 8080))
            self.controller_endpoint = f"http://localhost:{self.server_port}"
            self.config["controller_endpoint"] = self.controller_endpoint
            ready = self._wait_until_ready(timeout_sec=float(self.config.get("ready_timeout_sec", 300)))
            out["ready"] = ready
        self.history.append(out)
        return out

    def stop_container(self, *, on_event: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        if not self.container_id:
            out = {"event": "gui.container.stop", "skipped": True}
            self.history.append(out)
            return out
        cmd = ["docker", "rm", "-f", self.container_id]
        command_text = " ".join(cmd)
        if callable(on_event):
            try:
                on_event({"event": "runtime.env.command.start", "command_text": command_text})
            except Exception:
                pass
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = {
            "event": "gui.container.stop",
            "container_id": self.container_id,
            "exit_code": int(proc.returncode),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
        if callable(on_event):
            try:
                if out["stdout"]:
                    on_event({"event": "runtime.env.command.stdout", "command_text": command_text, "chunk": out["stdout"]})
                if out["stderr"]:
                    on_event({"event": "runtime.env.command.stderr", "command_text": command_text, "chunk": out["stderr"]})
                on_event({"event": "runtime.env.command.finish", "command_text": command_text, "exit_code": int(proc.returncode)})
            except Exception:
                pass
        self.container_id = None
        self.controller_endpoint = None
        self.server_port = None
        self.chromium_port = None
        self.vnc_port = None
        self.vlc_port = None
        self.history.append(out)
        return out

    def container_logs(
        self,
        *,
        tail: int = 200,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not self.container_id:
            out = {"event": "gui.container.logs", "skipped": True}
            self.history.append(out)
            return out
        cmd = ["docker", "logs", "--tail", str(max(1, int(tail))), self.container_id]
        command_text = " ".join(cmd)
        if callable(on_event):
            try:
                on_event({"event": "runtime.env.command.start", "command_text": command_text})
            except Exception:
                pass
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = {
            "event": "gui.container.logs",
            "container_id": self.container_id,
            "command": cmd,
            "exit_code": int(proc.returncode),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
        if callable(on_event):
            try:
                if out["stdout"]:
                    on_event({"event": "runtime.env.command.stdout", "command_text": command_text, "chunk": out["stdout"]})
                if out["stderr"]:
                    on_event({"event": "runtime.env.command.stderr", "command_text": command_text, "chunk": out["stderr"]})
                on_event({"event": "runtime.env.command.finish", "command_text": command_text, "exit_code": int(proc.returncode)})
            except Exception:
                pass
        self.history.append(out)
        return out

    def _wait_until_ready(self, *, timeout_sec: float = 300.0) -> bool:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            return False
        deadline = time.time() + max(1.0, timeout_sec)
        while time.time() < deadline:
            try:
                resp = requests.get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
                if resp.status_code == 200 and resp.content:
                    evt = {"event": "gui.container.ready", "endpoint": endpoint, "status_code": 200}
                    self.history.append(evt)
                    return True
            except Exception as exc:
                self.history.append({"event": "gui.container.wait", "endpoint": endpoint, "error": str(exc)})
            time.sleep(1.0)
        self.history.append({"event": "gui.container.ready_timeout", "endpoint": endpoint, "timeout_sec": timeout_sec})
        return False

    def observe(
        self,
        *,
        include_accessibility: bool | None = None,
        include_terminal: bool | None = None,
    ) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        obs = {}
        if endpoint:
            # /screenshot (OSWorld strict)
            try:
                resp = requests.get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
                content_type = resp.headers.get("Content-Type", "")
                content = resp.content if resp.status_code == 200 else b""
                # 必须是 image/png 且 magic 正确
                if resp.status_code == 200 and content_type.startswith("image/png") and content[:8] == b"\x89PNG\r\n\x1a\n":
                    obs["screenshot"] = content
                    obs["screenshot_ok"] = True
                else:
                    obs["screenshot"] = b""
                    obs["screenshot_ok"] = False
                    obs["screenshot_error"] = f"Invalid screenshot: status={resp.status_code}, content_type={content_type}"
                obs["status_code"] = resp.status_code
            except Exception as exc:
                obs["screenshot"] = b""
                obs["screenshot_ok"] = False
                obs["screenshot_error"] = str(exc)
            # /accessibility
            if include_accessibility:
                try:
                    a11y = requests.get(f"{endpoint.rstrip('/')}/accessibility", timeout=20)
                    obs["accessibility_status_code"] = a11y.status_code
                    if a11y.status_code == 200:
                        payload = a11y.json() if hasattr(a11y, "json") else {}
                        obs["accessibility_tree"] = str((payload or {}).get("AT") or "")
                    else:
                        obs["accessibility_tree"] = ""
                except Exception as exc:
                    obs["accessibility_error"] = str(exc)
            # /terminal
            if include_terminal:
                try:
                    terminal = requests.get(f"{endpoint.rstrip('/')}/terminal", timeout=20)
                    obs["terminal_status_code"] = terminal.status_code
                    if terminal.status_code == 200:
                        payload = terminal.json() if hasattr(terminal, "json") else {}
                        obs["terminal_output"] = str((payload or {}).get("output") or "")
                    else:
                        obs["terminal_output"] = ""
                except Exception as exc:
                    obs["terminal_error"] = str(exc)
        self._last_observation = obs
        self.history.append({"event": "gui.observe", **{k: v for k, v in obs.items() if k != "screenshot"}})
        return obs

    def execute_action(self, action: Mapping[str, Any]) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        action_dict = dict(action)
        payload = self._action_to_execute_payload(action_dict)
        if payload is None:
            out = {"event": "gui.action", "action": action_dict, "skipped": True}
            self.history.append(out)
            return out
        if endpoint:
            try:
                resp = requests.post(f"{endpoint.rstrip('/')}/execute", json=payload, timeout=60)
                out = {
                    "event": "gui.action",
                    "action": action_dict,
                    "status_code": resp.status_code,
                    "body": resp.text,
                    "payload": payload,
                }
                self.history.append(out)
                return out
            except Exception as exc:
                out = {"event": "gui.action_error", "action": action_dict, "error": str(exc)}
                self.history.append(out)
                return out
        out = {"event": "gui.action", "action": action_dict, "simulated": True}
        self.history.append(out)
        return out

    def _action_to_execute_payload(self, action: dict[str, Any]) -> dict[str, Any] | None:
        action_type = str(action.get("action_type") or "").upper()
        params = dict(action.get("parameters") or {})
        if action_type in {"DONE", "FAIL", "TERMINATE"}:
            return None
        if action_type == "WAIT":
            sec = float(params.get("time", params.get("seconds", 1.0)))
            time.sleep(max(0.0, sec))
            return None
        if action_type in {"MOVE_TO", "MOUSE_MOVE"}:
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            duration = float(params.get("duration", 0.0))
            return self._python_payload(f"pyautogui.moveTo({x}, {y}, duration={duration})")
        if action_type == "CLICK":
            kwargs: list[str] = []
            if "button" in params:
                kwargs.append(f"button={repr(str(params.get('button')))}")
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            if "num_clicks" in params:
                kwargs.append(f"clicks={int(params.get('num_clicks', 1))}")
            return self._python_payload(f"pyautogui.click({', '.join(kwargs)})")
        if action_type == "RIGHT_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            return self._python_payload(f"pyautogui.rightClick({', '.join(kwargs)})")
        if action_type == "DOUBLE_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            return self._python_payload(f"pyautogui.doubleClick({', '.join(kwargs)})")
        if action_type == "MOUSE_DOWN":
            if "button" in params:
                return self._python_payload(f"pyautogui.mouseDown(button={repr(str(params.get('button')))})")
            return self._python_payload("pyautogui.mouseDown()")
        if action_type == "MOUSE_UP":
            if "button" in params:
                return self._python_payload(f"pyautogui.mouseUp(button={repr(str(params.get('button')))})")
            return self._python_payload("pyautogui.mouseUp()")
        if action_type in {"DRAG_TO", "DRAG"}:
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            duration = float(params.get("duration", 1.0))
            button = str(params.get("button", "left"))
            return self._python_payload(
                f"pyautogui.dragTo({x}, {y}, duration={duration}, button={repr(button)}, mouseDownUp=True)"
            )
        if action_type == "SCROLL":
            commands: list[str] = []
            if "dx" in params:
                commands.append(f"pyautogui.hscroll({int(params.get('dx', 0))})")
            if "dy" in params:
                commands.append(f"pyautogui.vscroll({int(params.get('dy', 0))})")
            if not commands:
                commands.append(f"pyautogui.vscroll({int(params.get('dy', -800))})")
            return self._python_payload("; ".join(commands))
        if action_type == "TYPING":
            text = str(params.get("text", ""))
            return self._python_payload(f"pyautogui.typewrite({repr(text)})")
        if action_type == "PRESS":
            key = str(params.get("key", "enter"))
            return self._python_payload(f"pyautogui.press({repr(key)})")
        if action_type == "KEY_DOWN":
            key = str(params.get("key", ""))
            return self._python_payload(f"pyautogui.keyDown({repr(key)})")
        if action_type == "KEY_UP":
            key = str(params.get("key", ""))
            return self._python_payload(f"pyautogui.keyUp({repr(key)})")
        if action_type == "HOTKEY":
            keys_raw = params.get("keys")
            if isinstance(keys_raw, str):
                keys = [keys_raw]
            elif isinstance(keys_raw, Sequence):
                keys = [str(k) for k in keys_raw if str(k)]
            else:
                keys = []
            if not keys:
                raise ValueError("HOTKEY action requires non-empty 'keys'.")
            keys_args = ", ".join(repr(k) for k in keys)
            return self._python_payload(f"pyautogui.hotkey({keys_args})")
        raise ValueError(f"Unsupported action_type: {action_type}")

    def _python_payload(self, command: str) -> dict[str, Any]:
        return {"command": ["python", "-c", f"import pyautogui; {command}"], "shell": False}

    def start_recording(self) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            out = {"event": "gui.record.start", "skipped": True}
            self.history.append(out)
            return out
        try:
            resp = requests.post(f"{endpoint.rstrip('/')}/start_recording", timeout=10)
            out = {
                "event": "gui.record.start",
                "status_code": int(resp.status_code),
                "ok": bool(resp.status_code == 200),
                "body": resp.text,
            }
        except Exception as exc:
            out = {"event": "gui.record.start", "ok": False, "error": str(exc)}
        self.history.append(out)
        return out

    def end_recording(self) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            out = {"event": "gui.record.stop", "skipped": True}
            self.history.append(out)
            return out
        try:
            resp = requests.post(f"{endpoint.rstrip('/')}/end_recording", stream=True, timeout=60)
            data = bytes(resp.content or b"")
            # 必须 status_code==200 且内容非空
            ok = bool(resp.status_code == 200 and data)
            out = {
                "event": "gui.record.stop",
                "status_code": int(resp.status_code),
                "ok": ok,
                "bytes": len(data),
                "recording_bytes": data,
                "body": resp.text if not ok else "",
            }
        except Exception as exc:
            out = {"event": "gui.record.stop", "ok": False, "error": str(exc), "bytes": 0}
        self.history.append({k: v for k, v in out.items() if k != "recording_bytes"})
        return out

    def save_recording(self, path: str) -> dict[str, Any]:
        result = self.end_recording()
        payload = bytes(result.get("recording_bytes") or b"")
        if not payload:
            out = {
                "event": "gui.record.save",
                "ok": False,
                "path": path,
                "bytes": 0,
                "reason": result.get("error") or result.get("body") or "empty recording",
            }
            self.history.append(out)
            return out
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)
        out = {
            "event": "gui.record.save",
            "ok": True,
            "path": str(file_path.resolve()),
            "bytes": len(payload),
        }
        self.history.append(out)
        return out

    def _osworld_reference_root(self) -> Path:
        root = Path(__file__).resolve().parents[2]
        return root / "references" / "OSWorld"

    def _ensure_osworld_import_path(self) -> Path:
        ref_root = self._osworld_reference_root()
        if not ref_root.exists():
            raise FileNotFoundError(f"OSWorld reference path not found: {ref_root}")
        root_str = str(ref_root.resolve())
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        return ref_root

    def _load_osworld_callable(self, *, category: str, func_name: str) -> Callable[..., Any]:
        key = (category, func_name)
        cached = _OSWORLD_FUNC_CACHE.get(key)
        if cached is not None:
            return cached

        ref_root = self._ensure_osworld_import_path()
        base = ref_root / "desktop_env" / "evaluators" / category
        if not base.exists():
            raise FileNotFoundError(f"OSWorld evaluator category path not found: {base}")

        pattern = re.compile(rf"^\s*def\s+{re.escape(func_name)}\s*\(", re.MULTILINE)
        target_module: str | None = None
        for py_file in sorted(base.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                target_module = f"desktop_env.evaluators.{category}.{py_file.stem}"
                break
        if not target_module:
            raise AttributeError(f"OSWorld {category} function not found: {func_name}")

        module = importlib.import_module(target_module)
        fn = getattr(module, func_name, None)
        if not callable(fn):
            raise AttributeError(f"OSWorld {category} function not callable: {func_name}")
        _OSWORLD_FUNC_CACHE[key] = fn
        return fn

    def _load_osworld_metric(self, func_name: str) -> Callable[..., Any]:
        return self._load_osworld_callable(category="metrics", func_name=func_name)

    def _load_osworld_getter(self, getter_type: str) -> Callable[..., Any]:
        return self._load_osworld_callable(category="getters", func_name=f"get_{getter_type}")

    def _resolve_eval_cache_dir(self, payload: Mapping[str, Any] | None) -> Path:
        payload = payload or {}
        explicit = str(payload.get("eval_cache_dir") or "").strip()
        if explicit:
            path = Path(explicit)
        else:
            root = Path(self.config.get("eval_cache_root") or ".snowl/osworld_eval_cache")
            token = str(payload.get("sample_id") or payload.get("task_id") or "default")
            token = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", token).strip(" ._") or "default"
            path = root / token
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _run_osworld_setup_step(self, *, step_type: str, parameters: Mapping[str, Any], endpoint: str) -> dict[str, Any]:
        step = str(step_type or "").strip().lower()
        params = dict(parameters or {})
        if step == "sleep":
            seconds = float(params.get("seconds", 1.0))
            time.sleep(max(0.0, seconds))
            return {"status_code": 200, "step_type": step, "slept_seconds": seconds}

        path_overrides = {
            "open": "/setup/open_file",
            "execute": "/setup/execute",
            "execute_with_verification": "/setup/execute_with_verification",
            "launch": "/setup/launch",
            "activate_window": "/setup/activate_window",
            "close_window": "/setup/close_window",
            "change_wallpaper": "/setup/change_wallpaper",
            "download": "/setup/download_file",
            "upload_file": "/setup/upload",
        }
        route = path_overrides.get(step, f"/setup/{step}")
        url = f"{endpoint.rstrip('/')}{route}"
        resp = requests.post(url, json=params, timeout=120)
        return {
            "status_code": int(resp.status_code),
            "step_type": step,
            "route": route,
            "ok": bool(resp.status_code == 200),
            "body": (resp.text or "")[:600],
        }

    def _run_osworld_setup(self, *, setup_config: Sequence[Any], endpoint: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for index, item in enumerate(setup_config, start=1):
            if not isinstance(item, Mapping):
                events.append({"index": index, "ok": False, "error": f"invalid setup item: {item!r}"})
                continue
            step_type = str(item.get("type") or "").strip()
            params = item.get("parameters")
            if not step_type or not isinstance(params, Mapping):
                events.append({"index": index, "ok": False, "error": f"invalid setup schema: {item!r}"})
                continue
            try:
                out = self._run_osworld_setup_step(
                    step_type=step_type,
                    parameters=dict(params),
                    endpoint=endpoint,
                )
                out["index"] = index
                events.append(out)
            except Exception as exc:
                events.append({"index": index, "step_type": step_type, "ok": False, "error": str(exc)})
                break
        return events

    def _evaluate_osworld(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        evaluator = payload.get("evaluator")
        if not isinstance(evaluator, Mapping):
            raise ValueError("Missing evaluator config in payload.")

        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            raise ValueError("Missing controller endpoint for OSWorld evaluation.")

        parsed = urlparse(endpoint)
        vm_ip = parsed.hostname or "localhost"
        server_port = int(parsed.port or 5000)

        self._ensure_osworld_import_path()
        from desktop_env.controllers.python import PythonController  # type: ignore[import-not-found]

        cache_dir = self._resolve_eval_cache_dir(payload)
        controller = PythonController(vm_ip=vm_ip, server_port=server_port)
        action_history = list(payload.get("action_history") or [])
        env = _OSWorldEvalContext(
            controller=controller,
            vm_ip=vm_ip,
            server_port=server_port,
            cache_dir=str(cache_dir),
            evaluator=dict(evaluator),
            action_history=action_history,
            enable_proxy=bool(payload.get("proxy", False)),
        )

        postconfig = evaluator.get("postconfig") or []
        post_events: list[dict[str, Any]] = []
        if isinstance(postconfig, Sequence) and not isinstance(postconfig, (str, bytes)):
            post_events = self._run_osworld_setup(setup_config=list(postconfig), endpoint=endpoint)

        func_cfg = evaluator.get("func")
        if func_cfg == "infeasible":
            if action_history:
                last_action = action_history[-1]
                if last_action == "FAIL" or (
                    isinstance(last_action, Mapping)
                    and str(last_action.get("action_type") or "").upper() == "FAIL"
                ):
                    return {"event": "gui.evaluate", "score": 1.0, "simulated": False, "postconfig": post_events}
            return {"event": "gui.evaluate", "score": 0.0, "simulated": False, "postconfig": post_events}
        if action_history:
            last_action = action_history[-1]
            if last_action == "FAIL" or (
                isinstance(last_action, Mapping)
                and str(last_action.get("action_type") or "").upper() == "FAIL"
            ):
                return {"event": "gui.evaluate", "score": 0.0, "simulated": False, "postconfig": post_events}

        def _getter_from_cfg(cfg: Any) -> Callable[..., Any] | None:
            if not isinstance(cfg, Mapping):
                return None
            getter_type = str(cfg.get("type") or "").strip()
            if not getter_type:
                return None
            return self._load_osworld_getter(getter_type)

        if isinstance(func_cfg, Sequence) and not isinstance(func_cfg, (str, bytes)):
            metric_fns = [self._load_osworld_metric(str(x)) for x in list(func_cfg)]
            result_cfgs = list(evaluator.get("result") or [])
            expected_cfgs = list(evaluator.get("expected") or [])
            result_getters = [_getter_from_cfg(cfg) for cfg in result_cfgs]
            expected_getters = [_getter_from_cfg(cfg) for cfg in expected_cfgs]
            options_cfg = evaluator.get("options")
            if isinstance(options_cfg, Sequence) and not isinstance(options_cfg, (str, bytes)):
                metric_options = [dict(x or {}) for x in list(options_cfg)]
            else:
                metric_options = [{} for _ in metric_fns]
            metric_conj = str(evaluator.get("conj") or "and").lower()
            per_metric: list[dict[str, Any]] = []
            scores: list[float] = []
            for idx, metric in enumerate(metric_fns):
                result_cfg = result_cfgs[idx] if idx < len(result_cfgs) else {}
                result_getter = result_getters[idx] if idx < len(result_getters) else None
                expected_cfg = expected_cfgs[idx] if idx < len(expected_cfgs) else None
                expected_getter = expected_getters[idx] if idx < len(expected_getters) else None
                opts = metric_options[idx] if idx < len(metric_options) else {}
                if not callable(result_getter):
                    raise ValueError(f"Missing result getter at index {idx}.")
                result_state = result_getter(env, result_cfg)
                if callable(expected_getter) and expected_cfg:
                    expected_state = expected_getter(env, expected_cfg)
                    score_value = float(metric(result_state, expected_state, **dict(opts or {})))
                else:
                    score_value = float(metric(result_state, **dict(opts or {})))
                per_metric.append({"index": idx, "metric": getattr(metric, "__name__", str(metric)), "score": score_value})
                scores.append(score_value)
                if metric_conj == "and" and score_value == 0.0:
                    return {
                        "event": "gui.evaluate",
                        "score": 0.0,
                        "simulated": False,
                        "postconfig": post_events,
                        "metrics": per_metric,
                    }
                if metric_conj == "or" and score_value == 1.0:
                    return {
                        "event": "gui.evaluate",
                        "score": 1.0,
                        "simulated": False,
                        "postconfig": post_events,
                        "metrics": per_metric,
                    }
            final = (sum(scores) / len(scores)) if (metric_conj == "and" and scores) else (max(scores) if scores else 0.0)
            return {
                "event": "gui.evaluate",
                "score": float(final),
                "simulated": False,
                "postconfig": post_events,
                "metrics": per_metric,
            }

        metric = self._load_osworld_metric(str(func_cfg))
        result_cfg = evaluator.get("result") or {}
        result_getter = _getter_from_cfg(result_cfg)
        if not callable(result_getter):
            raise ValueError("Missing result getter in evaluator config.")
        result_state = result_getter(env, result_cfg)
        expected_cfg = evaluator.get("expected")
        expected_getter = _getter_from_cfg(expected_cfg)
        options = dict(evaluator.get("options") or {})
        if callable(expected_getter) and isinstance(expected_cfg, Mapping):
            expected_state = expected_getter(env, expected_cfg)
            score = float(metric(result_state, expected_state, **options))
        else:
            score = float(metric(result_state, **options))
        return {
            "event": "gui.evaluate",
            "score": float(score),
            "simulated": False,
            "postconfig": post_events,
            "metric": getattr(metric, "__name__", str(metric)),
        }

    def evaluate(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload_dict = dict(payload or {})
        if isinstance(payload_dict.get("evaluator"), Mapping):
            try:
                out = self._evaluate_osworld(payload_dict)
                self.history.append(dict(out))
                return out
            except Exception as exc:
                out = {
                    "event": "gui.evaluate",
                    "score": 0.0,
                    "simulated": True,
                    "error": str(exc),
                    "mode": "osworld_evaluator_fallback",
                }
                self.history.append(out)
                return out

        done_status = str(payload_dict.get("done_status") or "").lower()
        if done_status in {"success", "done"}:
            score = 1.0
        elif done_status in {"failed", "fail"}:
            score = 0.0
        else:
            score = 0.0
        out = {"event": "gui.evaluate", "score": score, "simulated": True}
        self.history.append(out)
        return out
