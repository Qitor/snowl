"""TTY input pump for live keyboard interaction."""

from __future__ import annotations

import os
import select
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StdinInputPump:
    """Capture key presses from TTY and enqueue semantic tokens."""

    controller: Any
    poll_interval_s: float = 0.03
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _started: bool = field(default=False, init=False)
    _tty_fd: int | None = field(default=None, init=False, repr=False)
    _old_term_attrs: Any | None = field(default=None, init=False, repr=False)
    _mode: str = field(default="off", init=False, repr=False)

    def start(self) -> bool:
        if self._started:
            return True
        try:
            if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
                return False
            self._tty_fd = sys.stdin.fileno()
        except Exception:
            return False

        try:
            import tty
            import termios

            self._old_term_attrs = termios.tcgetattr(self._tty_fd)
            tty.setcbreak(self._tty_fd)
            self._mode = "raw"
        except Exception:
            self._old_term_attrs = None
            self._mode = "line"
            self._tty_fd = None

        self._stop.clear()
        target = self._run if self._mode == "raw" else self._run_line_mode
        self._thread = threading.Thread(target=target, name="snowl-stdin-pump", daemon=True)
        self._thread.start()
        self._started = True
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
            self._thread = None
        if self._tty_fd is not None and self._old_term_attrs is not None:
            try:
                import termios

                termios.tcsetattr(self._tty_fd, termios.TCSADRAIN, self._old_term_attrs)
            except Exception:
                pass
        self._tty_fd = None
        self._old_term_attrs = None
        self._started = False
        self._mode = "off"

    def mode(self) -> str:
        return self._mode

    def _enqueue(self, token: str) -> None:
        enqueue = getattr(self.controller, "enqueue_input", None)
        if callable(enqueue):
            enqueue(token)
            return
        queue = getattr(self.controller, "queued_inputs", None)
        if isinstance(queue, list):
            queue.append(token)

    def _command_start(self) -> None:
        fn = getattr(self.controller, "command_start", None)
        if callable(fn):
            fn("/")

    def _command_append(self, text: str) -> None:
        fn = getattr(self.controller, "command_append", None)
        if callable(fn):
            fn(text)

    def _command_backspace(self) -> None:
        fn = getattr(self.controller, "command_backspace", None)
        if callable(fn):
            fn()

    def _command_submit(self) -> str | None:
        fn = getattr(self.controller, "command_submit", None)
        if callable(fn):
            return fn()
        return None

    def _command_cancel(self) -> None:
        fn = getattr(self.controller, "command_cancel", None)
        if callable(fn):
            fn()

    def _command_history_prev(self) -> str | None:
        fn = getattr(self.controller, "command_history_prev", None)
        if callable(fn):
            return fn()
        return None

    def _command_history_next(self) -> str | None:
        fn = getattr(self.controller, "command_history_next", None)
        if callable(fn):
            return fn()
        return None

    def _command_complete(self) -> str | None:
        fn = getattr(self.controller, "command_complete", None)
        if callable(fn):
            return fn()
        return None

    def _run(self) -> None:
        assert self._tty_fd is not None
        command_mode = False
        command_buffer = ""
        esc_mode = False
        esc_buffer = ""

        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self._tty_fd], [], [], self.poll_interval_s)
            except Exception:
                time.sleep(self.poll_interval_s)
                continue
            if not r:
                continue
            try:
                data = os.read(self._tty_fd, 128).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if not data:
                continue

            for ch in data:
                if esc_mode:
                    esc_buffer += ch
                    if ch.isalpha() or ch == "~":
                        token = self._map_escape(esc_buffer)
                        if token:
                            if command_mode and token == "up":
                                updated = self._command_history_prev()
                                if isinstance(updated, str):
                                    command_buffer = updated
                            elif command_mode and token == "down":
                                updated = self._command_history_next()
                                if isinstance(updated, str):
                                    command_buffer = updated
                            else:
                                self._enqueue(token)
                        esc_mode = False
                        esc_buffer = ""
                    elif len(esc_buffer) > 6:
                        esc_mode = False
                        esc_buffer = ""
                    continue

                if ch == "\x1b":
                    esc_mode = True
                    esc_buffer = ""
                    continue

                if command_mode:
                    if ch in ("\r", "\n"):
                        token = self._command_submit() or command_buffer.strip()
                        if token:
                            self._enqueue(token)
                        command_mode = False
                        command_buffer = ""
                        continue
                    if ch in ("\x7f", "\b"):
                        command_buffer = command_buffer[:-1] if command_buffer else command_buffer
                        self._command_backspace()
                        continue
                    if ch == "\x03":
                        self._enqueue("p")
                        continue
                    if ch == "\t":
                        updated = self._command_complete()
                        if isinstance(updated, str) and updated:
                            command_buffer = updated
                        else:
                            command_buffer += " "
                            self._command_append(" ")
                        continue
                    if ch == "\x1b":
                        command_mode = False
                        command_buffer = ""
                        self._command_cancel()
                        continue
                    if ch.isprintable():
                        command_buffer += ch
                        self._command_append(ch)
                    continue

                if ch == "/":
                    command_mode = True
                    command_buffer = "/"
                    self._command_start()
                    continue
                if ch == ":":
                    command_mode = True
                    command_buffer = "/"
                    self._command_start()
                    continue
                if ch == "\t":
                    self._enqueue("tab")
                    continue
                if ch in ("\r", "\n"):
                    self._enqueue("enter")
                    continue
                if ch in ("?", "p", "f", "r", "a", "t", "m", "s", "v", "b", "x", "j", "k"):
                    self._enqueue(ch)
                    continue

    @staticmethod
    def _map_escape(seq: str) -> str | None:
        mapping = {
            "[A": "up",
            "[B": "down",
            "[Z": "shift+tab",
        }
        return mapping.get(seq)

    def _run_line_mode(self) -> None:
        while not self._stop.is_set():
            try:
                line = sys.stdin.readline()
            except Exception:
                time.sleep(self.poll_interval_s)
                continue
            if not line:
                time.sleep(self.poll_interval_s)
                continue
            token = line.strip()
            if token:
                self._enqueue(token)
