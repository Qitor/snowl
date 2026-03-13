"""Low-level substrate helper (command_runner) for environment backends.

Framework role:
- Encapsulates transport/process/backend primitives used by higher env adapters.

Runtime/usage wiring:
- Consumed by terminal/gui/sandbox environment implementations.
- Key top-level symbols in this file: `CommandRunnerResult`, `CommandRunner`.

Change guardrails:
- Keep API narrow and reusable; avoid introducing benchmark semantics here.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Callable, Mapping


EventSink = Callable[[dict[str, Any]], None] | None


@dataclass(frozen=True)
class CommandRunnerResult:
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    started_at_ms: int
    ended_at_ms: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "started_at_ms": self.started_at_ms,
            "ended_at_ms": self.ended_at_ms,
            "duration_ms": self.duration_ms,
        }


class CommandRunner:
    """Runs commands and emits `runtime.env.command.*` events."""

    def __init__(self, *, cwd: str | None = None) -> None:
        self._cwd = cwd

    @staticmethod
    def _emit(on_event: EventSink, event: dict[str, Any]) -> None:
        if on_event is None:
            return
        try:
            on_event(dict(event))
        except Exception:
            return

    def run(
        self,
        cmd: list[str],
        *,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
        on_event: EventSink = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        started = int(time.time() * 1000)
        command_text = " ".join(str(x) for x in cmd)
        self._emit(on_event, {"event": "runtime.env.command.start", "command_text": command_text})

        proc = subprocess.Popen(
            cmd,
            cwd=(cwd if cwd is not None else self._cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            env=dict(env or os.environ),
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        q: Queue[tuple[str, str | None]] = Queue()

        def _reader(stream: Any, stream_name: str) -> None:
            try:
                if stream is None:
                    return
                for line in iter(stream.readline, ""):
                    q.put((stream_name, line))
            finally:
                try:
                    if stream is not None:
                        stream.close()
                finally:
                    q.put((stream_name, None))

        t_out = threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        done_streams = 0
        timed_out = False
        while done_streams < 2:
            if timeout_seconds is not None and (time.time() * 1000 - started) > timeout_seconds * 1000:
                timed_out = True
                proc.kill()
                self._emit(
                    on_event,
                    {
                        "event": "runtime.env.command.timeout",
                        "command_text": command_text,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                break

            try:
                stream_name, chunk = q.get(timeout=0.1)
            except Empty:
                if proc.poll() is not None and done_streams >= 2:
                    break
                continue

            if chunk is None:
                done_streams += 1
                continue
            if stream_name == "stdout":
                stdout_parts.append(chunk)
            else:
                stderr_parts.append(chunk)
            self._emit(
                on_event,
                {
                    "event": f"runtime.env.command.{stream_name}",
                    "command_text": command_text,
                    "chunk": chunk.rstrip("\n"),
                },
            )

        t_out.join(timeout=0.2)
        t_err.join(timeout=0.2)
        if timed_out:
            exit_code = -9
        else:
            exit_code = int(proc.wait())

        ended = int(time.time() * 1000)
        result = CommandRunnerResult(
            command=list(cmd),
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=exit_code,
            timed_out=timed_out,
            started_at_ms=started,
            ended_at_ms=ended,
            duration_ms=max(0, ended - started),
        )
        self._emit(
            on_event,
            {
                "event": "runtime.env.command.finish",
                "command_text": command_text,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )
        return result.to_dict()
