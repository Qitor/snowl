"""Built-in terminal tools for terminalbench-like agents."""

from __future__ import annotations

from dataclasses import dataclass

from snowl.core import ToolSpec, build_tool_spec
from snowl.envs import TerminalEnv


@dataclass
class TerminalToolset:
    env: TerminalEnv

    def send_keys(
        self,
        keystrokes: str,
        is_blocking: bool = False,
        timeout_sec: float = 180.0,
    ) -> dict:
        """Send keystrokes to the terminal session.

        Args:
            keystrokes: Terminal input to send.
            is_blocking: Wait until completion when true.
            timeout_sec: Timeout used for blocking mode.
        """
        return self.env.send_keys(
            keystrokes=keystrokes,
            is_blocking=is_blocking,
            timeout_sec=timeout_sec,
        )

    def exec(self, command: str, timeout_sec: float = 180.0) -> dict:
        """Execute a shell command and return stdout/stderr/exit_code."""
        return self.env.exec(command, timeout_seconds=timeout_sec)

    def capture(self) -> str:
        """Capture current terminal output snapshot."""
        return self.env.capture()

    def wait(self, seconds: float) -> dict:
        """Wait for a given number of seconds."""
        return self.env.wait(seconds)


def build_terminal_tools(env: TerminalEnv) -> list[ToolSpec]:
    bundle = TerminalToolset(env=env)
    return [
        build_tool_spec(
            bundle.send_keys,
            name="terminal_send_keys",
            description="Send terminal keystrokes (optional blocking).",
            required_ops=["terminal.send_keys"],
        ),
        build_tool_spec(
            bundle.exec,
            name="terminal_exec",
            description="Execute a shell command in terminal environment.",
            required_ops=["terminal.exec", "process.run"],
        ),
        build_tool_spec(
            bundle.capture,
            name="terminal_capture",
            description="Capture latest terminal output.",
            required_ops=["terminal.capture"],
        ),
        build_tool_spec(
            bundle.wait,
            name="terminal_wait",
            description="Wait for a number of seconds.",
            required_ops=["terminal.wait"],
        ),
    ]

