"""InstalledAgent: run real agents (Claude Code, Codex CLI, Aider) in containers.

Framework role:
- Defines InstalledAgent base class for containerized agent evaluation.
- Provides declarative CLI flag and environment variable mapping.
- Ships concrete implementations for popular coding agents.

Runtime/usage wiring:
- Used when evaluating real-world coding agents inside sandbox environments.
- Depends on EnvironmentProvider.execute() for container command execution.

Change guardrails:
- InstalledAgent must implement the Agent Protocol (agent_id + async run).
- Concrete agents must declare cli_flags and env_vars for parameter mapping.
- No direct dependency on specific container runtimes — uses EnvironmentProvider ABC.

Reference:
- ``references/harbor/src/harbor/agents/installed/base.py`` (BaseInstalledAgent)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.envs.provider import EnvironmentHandle, EnvironmentProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Declarative parameter mapping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CLIFlag:
    """Maps a logical parameter name to a CLI flag.

    Example::

        CLIFlag(name="model", flag="--model", default="sonnet")
        # Renders: --model sonnet

        CLIFlag(name="output", flag="--output", value_separator="=")
        # Renders: --output=value
    """

    name: str
    flag: str
    value_separator: str = " "
    default: str | None = None
    required: bool = False


@dataclass(frozen=True)
class EnvVar:
    """Maps a logical parameter name to an environment variable.

    Example::

        EnvVar(name="api_key", env_key="ANTHROPIC_API_KEY", required=True)
    """

    name: str
    env_key: str
    default: str | None = None
    required: bool = False


# ---------------------------------------------------------------------------
# InstalledAgent base class
# ---------------------------------------------------------------------------

class InstalledAgent:
    """Base class for agents installed in container environments.

    Unlike ChatAgent/ReActAgent which call a model API, InstalledAgent
    runs an external tool inside a container and parses its output.

    Implements the Agent Protocol (``agent_id`` + ``async run()``).
    """

    def __init__(
        self,
        *,
        agent_id: str = "installed",
        cli_command: str = "",
        cli_flags: dict[str, CLIFlag] | None = None,
        env_vars: dict[str, EnvVar] | None = None,
        setup_commands: tuple[str, ...] = (),
        timeout_seconds: float = 300.0,
    ) -> None:
        self.agent_id = agent_id
        self.cli_command = cli_command
        self.cli_flags = cli_flags or {}
        self.env_vars = env_vars or {}
        self.setup_commands = setup_commands
        self.timeout_seconds = timeout_seconds

    async def setup(
        self,
        environment: EnvironmentHandle,
        provider: EnvironmentProvider,
    ) -> None:
        """Install the agent in the container environment.

        Runs each command in ``setup_commands`` sequentially.
        """
        for cmd in self.setup_commands:
            result = await provider.execute(
                environment,
                cmd,
                timeout_seconds=self.timeout_seconds,
            )
            exit_code = result.get("exit_code", -1)
            if exit_code != 0:
                stderr = result.get("stderr", "")
                logger.warning(
                    "InstalledAgent.setup('%s') exited %d: %s",
                    cmd, exit_code, stderr[:200],
                )

    async def run(
        self,
        state: AgentState,
        context: AgentContext,
        tools: Sequence[Any] | None = None,
    ) -> AgentState:
        """Build CLI command, execute in environment, parse result.

        Requires ``context.metadata`` to contain:
        - ``environment_handle``: EnvironmentHandle instance
        - ``environment_provider``: EnvironmentProvider instance
        - Optional: ``agent_params``: dict for CLI flag/env var values
        """
        handle = context.metadata.get("environment_handle")
        provider = context.metadata.get("environment_provider")
        if handle is None or provider is None:
            logger.error("InstalledAgent.run: missing environment handle/provider in context.metadata")
            output = dict(state.output) if state.output else {}
            output["installed_agent_error"] = "missing environment_handle or environment_provider"
            state.output = output
            state.stop_reason = StopReason.ERROR
            return state

        # Extract instruction from the last user message
        instruction = self._extract_instruction(state)
        params = context.metadata.get("agent_params", {})

        # Build command and environment
        cmd = self.build_command(instruction, params)
        env = self.build_env(params)

        # Execute
        try:
            result = await provider.execute(
                handle,
                cmd,
                timeout_seconds=self.timeout_seconds,
                env=env if env else None,
            )
        except Exception as exc:
            logger.error("InstalledAgent.run: execution failed: %s", exc)
            output = dict(state.output) if state.output else {}
            output["installed_agent_error"] = str(exc)
            state.output = output
            state.stop_reason = StopReason.ERROR
            return state

        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")

        # Parse output
        parsed = self.parse_output(stdout, stderr, exit_code)

        # Update state
        output = dict(state.output) if state.output else {}
        output.update(parsed)
        output["installed_agent_id"] = self.agent_id
        output["installed_agent_exit_code"] = exit_code
        state.output = output

        # Add assistant message
        if stdout:
            messages = list(state.messages) if state.messages else []
            messages.append({"role": "assistant", "content": stdout[:5000]})
            state.messages = messages

        # Set stop reason
        if exit_code == 0:
            state.stop_reason = StopReason.COMPLETED
        else:
            state.stop_reason = StopReason.ERROR

        return state

    def build_command(
        self,
        instruction: str,
        params: dict[str, str] | None = None,
    ) -> str:
        """Build the CLI command string from instruction + params.

        Args:
            instruction: The task instruction (usually from the last user message).
            params: Optional parameter overrides for CLI flags.

        Returns:
            The assembled command string.
        """
        params = params or {}
        parts = [self.cli_command]

        # Add CLI flags
        for key, flag_def in self.cli_flags.items():
            value = params.get(key, flag_def.default)
            if value is not None:
                if flag_def.value_separator == "=":
                    parts.append(f"{flag_def.flag}={value}")
                else:
                    parts.append(flag_def.flag)
                    parts.append(str(value))
            elif flag_def.required:
                logger.warning(
                    "InstalledAgent: required flag '%s' has no value", key
                )

        # Add the instruction as the final argument
        if instruction:
            # Shell-escape the instruction
            escaped = instruction.replace("'", "'\\''")
            parts.append(f"'{escaped}'")

        return " ".join(parts)

    def build_env(
        self,
        params: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Build environment variable dict from params.

        Args:
            params: Optional parameter overrides for env vars.

        Returns:
            Dict of environment variable name → value.
        """
        params = params or {}
        env: dict[str, str] = {}

        for key, var_def in self.env_vars.items():
            value = params.get(key, var_def.default)
            if value is not None:
                env[var_def.env_key] = str(value)
            elif var_def.required:
                logger.warning(
                    "InstalledAgent: required env var '%s' (%s) has no value",
                    key, var_def.env_key,
                )

        return env

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> dict[str, Any]:
        """Parse the agent's CLI output into a normalized result.

        Override in subclasses for agent-specific parsing.

        Returns:
            Dict with parsed output fields.
        """
        return {
            "installed_agent_stdout": stdout[:10000] if stdout else "",
            "installed_agent_stderr": stderr[:2000] if stderr else "",
        }

    def _extract_instruction(self, state: AgentState) -> str:
        """Extract the instruction from the last user message in state."""
        if not state.messages:
            return ""
        # Walk backwards to find the last user message
        for msg in reversed(state.messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Multi-part content — concatenate text parts
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            parts.append(part.get("text", ""))
                    return " ".join(parts)
        return ""


# ---------------------------------------------------------------------------
# Concrete installed agents
# ---------------------------------------------------------------------------

class ClaudeCodeAgent(InstalledAgent):
    """Claude Code CLI agent — Anthropic's coding assistant."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id="claude_code",
            cli_command="claude",
            cli_flags={
                "model": CLIFlag(name="model", flag="--model", default="sonnet"),
                "max_turns": CLIFlag(name="max_turns", flag="--max-turns", default="10"),
                "output_format": CLIFlag(
                    name="output_format", flag="--output-format", default="json",
                ),
            },
            env_vars={
                "api_key": EnvVar(name="api_key", env_key="ANTHROPIC_API_KEY", required=True),
            },
            setup_commands=("npm install -g @anthropic-ai/claude-code",),
            **kwargs,
        )


class CodexCLIAgent(InstalledAgent):
    """OpenAI Codex CLI agent — automated coding assistant."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id="codex_cli",
            cli_command="codex",
            cli_flags={
                "model": CLIFlag(name="model", flag="--model", default="o4-mini"),
                "approval_mode": CLIFlag(
                    name="approval_mode", flag="--approval-mode", default="full-auto",
                ),
            },
            env_vars={
                "api_key": EnvVar(name="api_key", env_key="OPENAI_API_KEY", required=True),
            },
            setup_commands=("npm install -g @openai/codex",),
            **kwargs,
        )


class AiderAgent(InstalledAgent):
    """Aider — AI pair programming assistant."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id="aider",
            cli_command="aider",
            cli_flags={
                "model": CLIFlag(name="model", flag="--model", default="openai/gpt-4o"),
                "message": CLIFlag(name="message", flag="--message"),
                "no_auto_commits": CLIFlag(
                    name="no_auto_commits", flag="--no-auto-commits",
                ),
            },
            env_vars={
                "api_key": EnvVar(name="api_key", env_key="OPENAI_API_KEY", required=True),
            },
            setup_commands=("pip install aider-chat",),
            **kwargs,
        )
