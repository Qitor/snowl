"""GUI environment contract with optional Docker-backed runtime."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

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
        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        for c_port, h_port in (ports or {}).items():
            cmd += ["-p", f"{h_port}:{c_port}"]
        for host_path, container_path in (volumes or {}).items():
            cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
        for k, v in dict(env or {}).items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(image)
        command_text = " ".join(cmd)
        if callable(on_event):
            try:
                on_event({"event": "runtime.env.command.start", "command_text": command_text})
            except Exception:
                pass
        started = int(time.time() * 1000)
        proc = subprocess.run(cmd, capture_output=True, text=True)
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
        proc = subprocess.run(cmd, capture_output=True, text=True)
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

    def observe(self) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if endpoint:
            try:
                resp = requests.get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
                if resp.status_code == 200:
                    obs = {"screenshot": resp.content, "status_code": 200}
                    self._last_observation = obs
                    self.history.append({"event": "gui.observe", "status_code": 200})
                    return obs
            except Exception as exc:
                self.history.append({"event": "gui.observe_error", "error": str(exc)})
        obs = {"screenshot": b"", "status_code": None}
        self._last_observation = obs
        self.history.append({"event": "gui.observe", "status_code": None})
        return obs

    def execute_action(self, action: Mapping[str, Any]) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if endpoint:
            try:
                payload = self._action_to_execute_payload(dict(action))
                if payload is None:
                    out = {"event": "gui.action", "action": dict(action), "skipped": True}
                    self.history.append(out)
                    return out
                resp = requests.post(f"{endpoint.rstrip('/')}/execute", json=payload, timeout=60)
                out = {
                    "event": "gui.action",
                    "action": dict(action),
                    "status_code": resp.status_code,
                    "body": resp.text,
                    "payload": payload,
                }
                self.history.append(out)
                return out
            except Exception as exc:
                out = {"event": "gui.action_error", "action": dict(action), "error": str(exc)}
                self.history.append(out)
                return out
        out = {"event": "gui.action", "action": dict(action), "simulated": True}
        self.history.append(out)
        return out

    def _action_to_execute_payload(self, action: dict[str, Any]) -> dict[str, Any] | None:
        action_type = str(action.get("action_type") or "").upper()
        params = dict(action.get("parameters") or {})
        if action_type in {"DONE", "FAIL"}:
            return None
        if action_type == "WAIT":
            sec = float(params.get("time", 1.0))
            time.sleep(max(0.0, sec))
            return None

        py_code = ""
        if action_type == "CLICK":
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            button = str(params.get("button", "left"))
            clicks = int(params.get("num_clicks", 1))
            py_code = f"import pyautogui; pyautogui.click({x}, {y}, clicks={clicks}, button='{button}')"
        elif action_type == "TYPING":
            text = str(params.get("text", ""))
            safe = text.replace("\\", "\\\\").replace("'", "\\'")
            py_code = f"import pyautogui; pyautogui.write('{safe}')"
        elif action_type == "PRESS":
            key = str(params.get("key", "enter")).replace("\\", "\\\\").replace("'", "\\'")
            py_code = f"import pyautogui; pyautogui.press('{key}')"
        elif action_type == "SCROLL":
            dy = int(params.get("dy", -800))
            py_code = f"import pyautogui; pyautogui.scroll({dy})"
        else:
            return {"command": ["bash", "-lc", "echo unsupported action"], "shell": False}

        return {"command": ["python", "-c", py_code], "shell": False}

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
