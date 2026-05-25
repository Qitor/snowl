"""Tests for InstalledAgent: CLIFlag, EnvVar, build_command, build_env, run with mock environment."""

import pytest

from snowl.agents.installed import (
    AiderAgent,
    ClaudeCodeAgent,
    CLIFlag,
    CodexCLIAgent,
    EnvVar,
    InstalledAgent,
)
from snowl.core.agent import AgentContext, AgentState, StopReason
from snowl.core.agent import validate_agent


# ---------------------------------------------------------------------------
# CLIFlag / EnvVar
# ---------------------------------------------------------------------------

class TestCLIFlag:
    def test_construction(self):
        flag = CLIFlag(name="model", flag="--model", default="sonnet")
        assert flag.name == "model"
        assert flag.flag == "--model"
        assert flag.default == "sonnet"
        assert flag.required is False

    def test_frozen(self):
        flag = CLIFlag(name="model", flag="--model")
        with pytest.raises(AttributeError):
            flag.name = "other"

    def test_value_separator_default(self):
        flag = CLIFlag(name="m", flag="-m")
        assert flag.value_separator == " "

    def test_equals_separator(self):
        flag = CLIFlag(name="output", flag="--output", value_separator="=")
        assert flag.value_separator == "="


class TestEnvVar:
    def test_construction(self):
        var = EnvVar(name="api_key", env_key="API_KEY", required=True)
        assert var.name == "api_key"
        assert var.env_key == "API_KEY"
        assert var.required is True

    def test_frozen(self):
        var = EnvVar(name="x", env_key="X")
        with pytest.raises(AttributeError):
            var.name = "other"


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------

class TestBuildCommand:
    def test_simple_command(self):
        agent = InstalledAgent()
        agent.cli_command = "echo"
        agent.cli_flags = {}
        cmd = agent.build_command("hello")
        assert cmd == "echo 'hello'"

    def test_with_flags(self):
        agent = InstalledAgent()
        agent.cli_command = "tool"
        agent.cli_flags = {
            "model": CLIFlag(name="model", flag="--model", default="gpt4"),
        }
        cmd = agent.build_command("do stuff")
        assert "--model gpt4" in cmd
        assert "'do stuff'" in cmd

    def test_with_equals_separator(self):
        agent = InstalledAgent()
        agent.cli_command = "tool"
        agent.cli_flags = {
            "output": CLIFlag(name="output", flag="--output", value_separator="="),
        }
        cmd = agent.build_command("test", params={"output": "json"})
        assert "--output=json" in cmd

    def test_params_override_default(self):
        agent = InstalledAgent()
        agent.cli_command = "tool"
        agent.cli_flags = {
            "model": CLIFlag(name="model", flag="--model", default="gpt4"),
        }
        cmd = agent.build_command("test", params={"model": "sonnet"})
        assert "--model sonnet" in cmd
        assert "gpt4" not in cmd

    def test_required_flag_missing(self):
        agent = InstalledAgent()
        agent.cli_command = "tool"
        agent.cli_flags = {
            "key": CLIFlag(name="key", flag="--key", required=True),
        }
        # Should not crash, just log warning
        cmd = agent.build_command("test")
        assert "tool" in cmd

    def test_shell_escapes_instruction(self):
        agent = InstalledAgent()
        agent.cli_command = "echo"
        agent.cli_flags = {}
        cmd = agent.build_command("it's a test")
        assert "'it'\\''s a test'" in cmd


# ---------------------------------------------------------------------------
# build_env
# ---------------------------------------------------------------------------

class TestBuildEnv:
    def test_empty_env_vars(self):
        agent = InstalledAgent()
        agent.env_vars = {}
        assert agent.build_env() == {}

    def test_with_default(self):
        agent = InstalledAgent()
        agent.env_vars = {
            "key": EnvVar(name="key", env_key="MY_KEY", default="val"),
        }
        env = agent.build_env()
        assert env == {"MY_KEY": "val"}

    def test_params_override(self):
        agent = InstalledAgent()
        agent.env_vars = {
            "key": EnvVar(name="key", env_key="MY_KEY", default="default_val"),
        }
        env = agent.build_env(params={"key": "override_val"})
        assert env == {"MY_KEY": "override_val"}

    def test_required_missing(self):
        agent = InstalledAgent()
        agent.env_vars = {
            "key": EnvVar(name="key", env_key="MY_KEY", required=True),
        }
        # Should not crash, just log warning
        env = agent.build_env()
        assert env == {}


# ---------------------------------------------------------------------------
# InstalledAgent.run() with mock environment
# ---------------------------------------------------------------------------

class _MockProvider:
    """Mock EnvironmentProvider for testing."""

    def __init__(self, responses=None):
        self.responses = responses or [{"exit_code": 0, "stdout": "done", "stderr": ""}]
        self.call_log = []

    async def execute(self, handle, command, *, timeout_seconds=None, workdir=None, env=None):
        self.call_log.append({
            "command": command,
            "timeout": timeout_seconds,
            "env": env,
        })
        if self.responses:
            return self.responses.pop(0)
        return {"exit_code": 0, "stdout": "", "stderr": ""}


class _MockHandle:
    """Mock EnvironmentHandle."""

    def __init__(self):
        self.environment_id = "test-env"
        self.provider_name = "mock"


class TestInstalledAgentRun:
    @pytest.mark.asyncio
    async def test_run_success(self):
        agent = InstalledAgent()
        agent.agent_id = "test_agent"
        agent.cli_command = "echo"
        agent.cli_flags = {}

        provider = _MockProvider()
        handle = _MockHandle()

        state = AgentState(
            messages=[{"role": "user", "content": "say hello"}],
        )
        context = AgentContext(
            task_id="t1",
            metadata={
                "environment_handle": handle,
                "environment_provider": provider,
            },
        )

        result = await agent.run(state, context)
        assert result.stop_reason == StopReason.COMPLETED
        assert result.output["installed_agent_id"] == "test_agent"
        assert result.output["installed_agent_exit_code"] == 0
        assert len(provider.call_log) == 1
        assert "say hello" in provider.call_log[0]["command"]

    @pytest.mark.asyncio
    async def test_run_failure(self):
        agent = InstalledAgent()
        agent.agent_id = "test_agent"
        agent.cli_command = "false"
        agent.cli_flags = {}

        provider = _MockProvider(responses=[{"exit_code": 1, "stdout": "", "stderr": "error"}])
        handle = _MockHandle()

        state = AgentState(messages=[{"role": "user", "content": "do it"}])
        context = AgentContext(
            task_id="t1",
            metadata={
                "environment_handle": handle,
                "environment_provider": provider,
            },
        )

        result = await agent.run(state, context)
        assert result.stop_reason == StopReason.ERROR
        assert result.output["installed_agent_exit_code"] == 1

    @pytest.mark.asyncio
    async def test_run_missing_environment(self):
        agent = InstalledAgent()
        agent.agent_id = "test_agent"

        state = AgentState(messages=[{"role": "user", "content": "test"}])
        context = AgentContext(task_id="t1", metadata={})

        result = await agent.run(state, context)
        assert result.stop_reason == StopReason.ERROR
        assert "installed_agent_error" in result.output

    @pytest.mark.asyncio
    async def test_run_with_env_vars(self):
        agent = InstalledAgent()
        agent.agent_id = "test_agent"
        agent.cli_command = "tool"
        agent.cli_flags = {}
        agent.env_vars = {
            "api_key": EnvVar(name="api_key", env_key="API_KEY", required=True),
        }

        provider = _MockProvider()
        handle = _MockHandle()

        state = AgentState(messages=[{"role": "user", "content": "test"}])
        context = AgentContext(
            task_id="t1",
            metadata={
                "environment_handle": handle,
                "environment_provider": provider,
                "agent_params": {"api_key": "sk-test123"},
            },
        )

        result = await agent.run(state, context)
        assert provider.call_log[0]["env"] == {"API_KEY": "sk-test123"}


# ---------------------------------------------------------------------------
# InstalledAgent.setup() with mock environment
# ---------------------------------------------------------------------------

class TestInstalledAgentSetup:
    @pytest.mark.asyncio
    async def test_setup_runs_commands(self):
        agent = InstalledAgent()
        agent.setup_commands = ("echo install1", "echo install2")

        provider = _MockProvider(responses=[
            {"exit_code": 0, "stdout": "", "stderr": ""},
            {"exit_code": 0, "stdout": "", "stderr": ""},
        ])
        handle = _MockHandle()

        await agent.setup(handle, provider)
        assert len(provider.call_log) == 2
        assert provider.call_log[0]["command"] == "echo install1"
        assert provider.call_log[1]["command"] == "echo install2"


# ---------------------------------------------------------------------------
# Concrete agents
# ---------------------------------------------------------------------------

class TestClaudeCodeAgent:
    def test_agent_id(self):
        agent = ClaudeCodeAgent()
        assert agent.agent_id == "claude_code"

    def test_cli_command(self):
        agent = ClaudeCodeAgent()
        assert agent.cli_command == "claude"

    def test_has_flags(self):
        agent = ClaudeCodeAgent()
        assert "model" in agent.cli_flags
        assert agent.cli_flags["model"].flag == "--model"

    def test_has_env_vars(self):
        agent = ClaudeCodeAgent()
        assert "api_key" in agent.env_vars
        assert agent.env_vars["api_key"].env_key == "ANTHROPIC_API_KEY"

    def test_has_setup_commands(self):
        agent = ClaudeCodeAgent()
        assert len(agent.setup_commands) > 0
        assert "claude-code" in agent.setup_commands[0]

    def test_build_command(self):
        agent = ClaudeCodeAgent()
        cmd = agent.build_command("fix the bug")
        assert "claude" in cmd
        assert "--model sonnet" in cmd
        assert "'fix the bug'" in cmd


class TestCodexCLIAgent:
    def test_agent_id(self):
        agent = CodexCLIAgent()
        assert agent.agent_id == "codex_cli"

    def test_cli_command(self):
        agent = CodexCLIAgent()
        assert agent.cli_command == "codex"

    def test_has_env_vars(self):
        agent = CodexCLIAgent()
        assert "api_key" in agent.env_vars
        assert agent.env_vars["api_key"].env_key == "OPENAI_API_KEY"


class TestAiderAgent:
    def test_agent_id(self):
        agent = AiderAgent()
        assert agent.agent_id == "aider"

    def test_cli_command(self):
        agent = AiderAgent()
        assert agent.cli_command == "aider"

    def test_has_setup(self):
        agent = AiderAgent()
        assert "aider-chat" in agent.setup_commands[0]


# ---------------------------------------------------------------------------
# Agent Protocol conformance
# ---------------------------------------------------------------------------

class TestAgentProtocolConformance:
    def test_validate_claude_code(self):
        agent = ClaudeCodeAgent()
        validate_agent(agent)

    def test_validate_codex(self):
        agent = CodexCLIAgent()
        validate_agent(agent)

    def test_validate_aider(self):
        agent = AiderAgent()
        validate_agent(agent)

    def test_validate_base_installed(self):
        agent = InstalledAgent()
        agent.agent_id = "test"
        validate_agent(agent)
