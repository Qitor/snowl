"""GUI environment contract with optional Docker-backed runtime."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests

from snowl.core import EnvSpec, validate_env_spec


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

        env_dict = dict(env or {})
        kvm_device = "/dev/kvm"
        kvm_exists = os.path.exists(kvm_device)
        if not kvm_exists:
            env_dict.setdefault("KVM", "N")

        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        for cap in (cap_add or ()):
            cap_name = str(cap).strip()
            if cap_name:
                cmd += ["--cap-add", cap_name]
        if kvm_exists:
            cmd += ["--device", kvm_device]
        for c_port, h_port in (ports or {}).items():
            cmd += ["-p", f"{h_port}:{c_port}"]
        for host_path, container_path in (volumes or {}).items():
            cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
        for key, value in env_dict.items():
            cmd += ["-e", f"{key}={value}"]
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
        obs: dict[str, Any] = {"screenshot": b"", "status_code": None}
        if endpoint:
            try:
                resp = requests.get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
                obs["status_code"] = int(resp.status_code)
                if resp.status_code == 200:
                    obs["screenshot"] = bytes(resp.content or b"")
            except Exception as exc:
                obs["screenshot_error"] = str(exc)

            if include_accessibility:
                try:
                    a11y = requests.get(f"{endpoint.rstrip('/')}/accessibility", timeout=20)
                    obs["accessibility_status_code"] = int(a11y.status_code)
                    if a11y.status_code == 200:
                        payload = a11y.json() if hasattr(a11y, "json") else {}
                        obs["accessibility_tree"] = str((payload or {}).get("AT") or "")
                    else:
                        obs["accessibility_tree"] = ""
                except Exception as exc:
                    obs["accessibility_error"] = str(exc)

            if include_terminal:
                try:
                    terminal = requests.get(f"{endpoint.rstrip('/')}/terminal", timeout=20)
                    obs["terminal_status_code"] = int(terminal.status_code)
                    if terminal.status_code == 200:
                        payload = terminal.json() if hasattr(terminal, "json") else {}
                        obs["terminal_output"] = str((payload or {}).get("output") or "")
                    else:
                        obs["terminal_output"] = ""
                except Exception as exc:
                    obs["terminal_error"] = str(exc)

        self._last_observation = dict(obs)
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
                    "status_code": int(resp.status_code),
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
        if "command" in action:
            command = action.get("command")
            if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
                raise ValueError("command passthrough must be a sequence of args.")
            return {"command": [str(x) for x in command], "shell": bool(action.get("shell", False))}

        action_type = str(action.get("action_type") or "").upper()
        if action_type == "TYPE":
            action_type = "TYPING"
        elif action_type == "KEY":
            key_raw = str(action.get("key", "") or "")
            if "+" in key_raw:
                action_type = "HOTKEY"
            else:
                action_type = "PRESS"
        params = dict(action.get("parameters") or {})
        if not params:
            for key in (
                "x",
                "y",
                "button",
                "click_type",
                "num_clicks",
                "dx",
                "dy",
                "text",
                "key",
                "keys",
                "duration",
                "seconds",
                "time",
            ):
                if key in action:
                    params[key] = action.get(key)
        click_type = str(params.get("click_type", "")).strip().lower()
        if click_type and "button" not in params:
            if click_type in {"left", "right", "middle"}:
                params["button"] = click_type
            params.pop("click_type", None)
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
            code = f"pyautogui.click({', '.join(kwargs)})" if kwargs else "pyautogui.click()"
            return self._python_payload(code)
        if action_type == "RIGHT_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            code = f"pyautogui.rightClick({', '.join(kwargs)})" if kwargs else "pyautogui.rightClick()"
            return self._python_payload(code)
        if action_type == "DOUBLE_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            code = f"pyautogui.doubleClick({', '.join(kwargs)})" if kwargs else "pyautogui.doubleClick()"
            return self._python_payload(code)
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
                if "+" in keys_raw:
                    keys = [x.strip() for x in keys_raw.split("+") if x.strip()]
                else:
                    keys = [keys_raw]
            elif isinstance(keys_raw, Sequence):
                keys = [str(k) for k in keys_raw if str(k)]
            else:
                keys = []
            if not keys and "key" in params:
                key_raw = str(params.get("key", "") or "")
                if "+" in key_raw:
                    keys = [x.strip() for x in key_raw.split("+") if x.strip()]
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
            resp = requests.post(f"{endpoint.rstrip('/')}/start_recording", timeout=30)
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
            resp = requests.post(f"{endpoint.rstrip('/')}/end_recording", timeout=120)
            data = bytes(resp.content or b"")
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

    def evaluate(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        done_status = str((payload or {}).get("done_status") or "").lower()
        if done_status in {"success", "done"}:
            score = 1.0
        elif done_status in {"failed", "fail"}:
            score = 0.0
        else:
            score = 0.0
        out = {"event": "gui.evaluate", "score": score, "simulated": True}
        self.history.append(out)
        return out
