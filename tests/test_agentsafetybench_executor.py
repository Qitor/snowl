"""Tests for AgentSafetyBench env_loader and executor modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from snowl.benchmarks.agentsafetybench.env_loader import (
    SnowlBaseEnv,
    list_available_environments,
    load_environment_class,
    load_tool_schemas,
)
from snowl.benchmarks.agentsafetybench.executor import (
    AGENTSAFETYBENCH_SENTINEL,
    AgentSafetyBenchExecutor,
    make_agentsafetybench_stub_tool,
)


# ---------------------------------------------------------------------------
# Fixtures: minimal fake environment dir
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_env_dir(tmp_path: Path) -> Path:
    """Create a minimal fake environment with .py and .json files."""
    env_dir = tmp_path / "environments"
    env_dir.mkdir()

    # Simple environment .py that inherits from BaseEnv (injected by loader)
    py_code = (
        "class FakeCalculator(BaseEnv):\n"
        "    def add(self, a, b):\n"
        "        return {'success': True, 'result': int(a) + int(b)}\n"
        "    def multiply(self, a, b):\n"
        "        return {'success': True, 'result': int(a) * int(b)}\n"
    )
    (env_dir / "FakeCalculator.py").write_text(py_code, encoding="utf-8")

    # Matching .json schema
    schemas = [
        {
            "name": "add",
            "description": "Add two numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        },
        {
            "name": "multiply",
            "description": "Multiply two numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        },
    ]
    (env_dir / "FakeCalculator.json").write_text(json.dumps(schemas), encoding="utf-8")
    return env_dir


# ---------------------------------------------------------------------------
# env_loader tests
# ---------------------------------------------------------------------------


class TestSnowlBaseEnv:
    def test_init_reads_json_schema(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        assert instance.tool_list == ["add", "multiply"]
        assert len(instance.tool_descs) == 2

    def test_has_tool(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        assert instance.has_tool("add") is True
        assert instance.has_tool("nonexistent") is False

    def test_get_tool_descs(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        descs = instance.get_tool_descs(["add"])
        assert len(descs) == 1
        assert descs[0]["name"] == "add"

    def test_get_tool_descs_missing_raises(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        with pytest.raises(RuntimeError, match="not found"):
            instance.get_tool_descs(["nonexistent"])

    def test_call_tool(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        result = instance.call_tool("add", {"a": 3, "b": 4})
        assert result == {"success": True, "result": 7}

    def test_call_tool_invalid_name(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        result = instance.call_tool("nonexistent", {})
        assert result["success"] is False

    def test_call_tool_missing_required_param(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        instance = cls()
        result = instance.call_tool("add", {"a": 1})
        assert result["success"] is False
        assert "Missing" in result["message"]


class TestLoadEnvironmentClass:
    def test_loads_class_with_shim(self, fake_env_dir: Path) -> None:
        cls = load_environment_class("FakeCalculator", fake_env_dir)
        assert cls.__name__ == "FakeCalculator"
        assert issubclass(cls, SnowlBaseEnv)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_environment_class("Nonexistent", tmp_path)

    def test_missing_class_in_module_raises(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "envs"
        env_dir.mkdir()
        (env_dir / "WrongName.py").write_text("class NotWrongName(BaseEnv): pass\n", encoding="utf-8")
        with pytest.raises(AttributeError, match="no class"):
            load_environment_class("WrongName", env_dir)


class TestLoadToolSchemas:
    def test_loads_all_schemas(self, fake_env_dir: Path) -> None:
        schemas = load_tool_schemas("FakeCalculator", fake_env_dir)
        assert len(schemas) == 2
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "add"

    def test_filters_by_tool_names(self, fake_env_dir: Path) -> None:
        schemas = load_tool_schemas("FakeCalculator", fake_env_dir, tool_names=["add"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "add"

    def test_missing_json_returns_empty(self, tmp_path: Path) -> None:
        schemas = load_tool_schemas("Nonexistent", tmp_path)
        assert schemas == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "envs"
        env_dir.mkdir()
        (env_dir / "Bad.json").write_text('"not an array"', encoding="utf-8")
        schemas = load_tool_schemas("Bad", env_dir)
        assert schemas == []


class TestListAvailableEnvironments:
    def test_lists_environments(self, fake_env_dir: Path) -> None:
        names = list_available_environments(fake_env_dir)
        assert "FakeCalculator" in names

    def test_skips_baseenv_and_envmanager(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "envs"
        env_dir.mkdir()
        for name in ("BaseEnv", "EnvManager", "__init__"):
            (env_dir / f"{name}.py").write_text("", encoding="utf-8")
            (env_dir / f"{name}.json").write_text("[]", encoding="utf-8")
        names = list_available_environments(env_dir)
        assert "BaseEnv" not in names
        assert "EnvManager" not in names
        assert "__init__" not in names

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        names = list_available_environments(tmp_path / "nope")
        assert names == []


# ---------------------------------------------------------------------------
# executor tests
# ---------------------------------------------------------------------------


class TestMakeStubTool:
    def test_creates_stub_returning_sentinel(self) -> None:
        stub = make_agentsafetybench_stub_tool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        assert stub.name == "test_tool"
        result = stub.callable()
        assert result == AGENTSAFETYBENCH_SENTINEL


class TestAgentSafetyBenchExecutor:
    @pytest.mark.asyncio()
    async def test_intercept_call_passes_through(self, fake_env_dir: Path) -> None:
        executor = AgentSafetyBenchExecutor(
            env_name="FakeCalculator",
            tool_names=["add"],
            env_dir=str(fake_env_dir),
        )
        args = {"a": 1, "b": 2}
        result = await executor.intercept_call("add", args)
        assert result == args

    @pytest.mark.asyncio()
    async def test_intercept_result_sentinel_delegates_to_env(self, fake_env_dir: Path) -> None:
        executor = AgentSafetyBenchExecutor(
            env_name="FakeCalculator",
            tool_names=["add"],
            env_dir=str(fake_env_dir),
        )
        result = await executor.intercept_result(
            "add",
            {"a": 3, "b": 4},
            AGENTSAFETYBENCH_SENTINEL,
        )
        assert result == {"success": True, "result": 7}

    @pytest.mark.asyncio()
    async def test_intercept_result_non_sentinel_passes_through(self, fake_env_dir: Path) -> None:
        executor = AgentSafetyBenchExecutor(
            env_name="FakeCalculator",
            tool_names=["add"],
            env_dir=str(fake_env_dir),
        )
        original = {"some": "data"}
        result = await executor.intercept_result("add", {}, original)
        assert result is original

    @pytest.mark.asyncio()
    async def test_intercept_result_env_error_returns_failure(self, fake_env_dir: Path) -> None:
        executor = AgentSafetyBenchExecutor(
            env_name="FakeCalculator",
            tool_names=["add"],
            env_dir=str(fake_env_dir),
        )
        # Calling a tool that doesn't exist on the env
        result = await executor.intercept_result(
            "nonexistent_tool",
            {},
            AGENTSAFETYBENCH_SENTINEL,
        )
        assert isinstance(result, dict)
        assert result["success"] is False

    def test_executor_with_env_params(self, fake_env_dir: Path) -> None:
        """Executor accepts env_params without crashing (env __init__ may ignore them)."""
        executor = AgentSafetyBenchExecutor(
            env_name="FakeCalculator",
            env_params={"key": "value"},
            tool_names=["add"],
            env_dir=str(fake_env_dir),
        )
        assert executor.env_name == "FakeCalculator"
