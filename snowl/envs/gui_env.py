"""GUI environment adapter over container + HTTP control plane (OSWorld-style workflows).

Framework role:
- Starts/stops GUI containers, waits for readiness, executes UI actions, and captures observations/snapshots.
- Persists operation history for debugging and emits structured events consumed by monitor views.

Runtime/usage wiring:
- Used by GUI-capable container providers and toolsets during trial execution and teardown.

Change guardrails:
- Keep action payload and observation shape stable; benchmark evaluators/tools parse these structures.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from snowl.core import EnvSpec, validate_env_spec
from snowl.envs.substrate import (
    CommandRunner,
    ContainerBackend,
    GuiActionTranslator,
    HttpRunner,
)


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
    _command_runner: CommandRunner | None = field(default=None, init=False, repr=False)
    _container_backend: ContainerBackend | None = field(default=None, init=False, repr=False)
    _http_runner: HttpRunner | None = field(default=None, init=False, repr=False)
    _action_translator: GuiActionTranslator = field(default_factory=GuiActionTranslator, init=False, repr=False)

    def __post_init__(self) -> None:
        validate_env_spec(self.env_spec)
        workdir = str(Path(str(self.config.get("workdir") or Path.cwd())).resolve())
        self._command_runner = CommandRunner(cwd=workdir)
        self._container_backend = ContainerBackend(command_runner=self._command_runner)
        self._http_runner = HttpRunner(
            default_retries=int(self.config.get("http_retries", 0) or 0),
            default_retry_backoff_sec=float(self.config.get("http_retry_backoff_sec", 0.25) or 0.25),
        )

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

    def _backend(self) -> ContainerBackend:
        return self._container_backend or ContainerBackend(
            command_runner=self._command_runner or CommandRunner(cwd=str(Path.cwd()))
        )

    def _http(self) -> HttpRunner:
        return self._http_runner or HttpRunner()

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

        started = self._backend().run(
            image=str(image),
            env=env_dict,
            ports=ports,
            volumes=volumes,
            cap_add=cap_add,
            devices=[kvm_device] if kvm_exists else None,
            detach=detach,
            on_event=on_event,
        )
        out = {
            "event": "gui.container.start",
            "command": list(started.get("command") or []),
            "exit_code": int(started.get("exit_code", 1) if started.get("exit_code") is not None else 1),
            "stdout": str(started.get("stdout") or "").strip(),
            "stderr": str(started.get("stderr") or "").strip(),
            "started_at_ms": int(started.get("started_at_ms", 0) or 0),
            "ended_at_ms": int(started.get("ended_at_ms", 0) or 0),
            "duration_ms": int(started.get("duration_ms", 0) or 0),
        }
        if out["exit_code"] == 0:
            self.container_id = out["stdout"].splitlines()[0][:64]
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

        stopped = self._backend().rm(
            self.container_id,
            force=True,
            on_event=on_event,
        )
        out = {
            "event": "gui.container.stop",
            "container_id": self.container_id,
            "exit_code": int(stopped.get("exit_code", 1) if stopped.get("exit_code") is not None else 1),
            "stdout": str(stopped.get("stdout") or "").strip(),
            "stderr": str(stopped.get("stderr") or "").strip(),
        }
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

        logs_out = self._backend().logs(
            self.container_id,
            tail=tail,
            on_event=on_event,
        )
        out = {
            "event": "gui.container.logs",
            "container_id": self.container_id,
            "command": list(logs_out.get("command") or []),
            "exit_code": int(logs_out.get("exit_code", 1) if logs_out.get("exit_code") is not None else 1),
            "stdout": str(logs_out.get("stdout") or "").strip(),
            "stderr": str(logs_out.get("stderr") or "").strip(),
        }
        self.history.append(out)
        return out

    def _wait_until_ready(self, *, timeout_sec: float = 300.0) -> bool:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            return False
        deadline = time.time() + max(1.0, timeout_sec)
        while time.time() < deadline:
            try:
                resp = self._http().get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
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
                resp = self._http().get(f"{endpoint.rstrip('/')}/screenshot", timeout=10)
                obs["status_code"] = int(resp.status_code)
                if resp.status_code == 200:
                    obs["screenshot"] = bytes(resp.content or b"")
            except Exception as exc:
                obs["screenshot_error"] = str(exc)

            if include_accessibility:
                try:
                    a11y = self._http().get(f"{endpoint.rstrip('/')}/accessibility", timeout=20)
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
                    terminal = self._http().get(f"{endpoint.rstrip('/')}/terminal", timeout=20)
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
                resp = self._http().post(f"{endpoint.rstrip('/')}/execute", json=payload, timeout=60)
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
        return self._action_translator.to_execute_payload(action)

    def _python_payload(self, command: str) -> dict[str, Any]:
        return {"command": ["python", "-c", f"import pyautogui; {command}"], "shell": False}

    def start_recording(self) -> dict[str, Any]:
        endpoint = str(self.config.get("controller_endpoint") or self.controller_endpoint or "")
        if not endpoint:
            out = {"event": "gui.record.start", "skipped": True}
            self.history.append(out)
            return out
        try:
            resp = self._http().post(f"{endpoint.rstrip('/')}/start_recording", timeout=30)
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
            resp = self._http().post(f"{endpoint.rstrip('/')}/end_recording", timeout=120)
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
