"""Dynamic environment loader for Agent-SafetyBench without reference package imports.

Provides a Snowl-native ``SnowlBaseEnv`` shim that replaces the reference
repo's ``BaseEnv``, plus loader functions that dynamically import environment
.py files and read .json tool schemas -- all without adding the reference
package to ``sys.path``.

Framework role:
- Bridges Agent-SafetyBench's 350 environment modules into Snowl's tool middleware
  chain via ``AgentSafetyBenchExecutor``.

Runtime/usage wiring:
- Consumed by ``executor.py`` and ``adapter.py`` to create tool stubs and
  resolve tool schemas for each sample.

Change guardrails:
- Must NOT import from the Agent-SafetyBench Python package.
- ``SnowlBaseEnv`` must stay API-compatible with the reference ``BaseEnv``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


AGENTSAFETYBENCH_ENV_DIR: Path = _project_root() / "references" / "Agent-SafetyBench" / "environments"


class SnowlBaseEnv:
    """Drop-in replacement for Agent-SafetyBench's BaseEnv.

    Reimplements the key methods from the reference ``BaseEnv`` so that
    environment .py files can run without importing from the reference package.
    The critical difference: the JSON schema directory is set by the loader
    rather than derived from ``__file__`` of the reference package.
    """

    _env_json_dir: str = ""  # Set by the loader before __init__ runs

    def __init__(self, **kwargs: Any) -> None:
        self.tool_list: list[str] = []
        class_name = self.__class__.__name__
        dirpath = Path(self._env_json_dir) if self._env_json_dir else Path(".")
        schema_path = dirpath / f"{class_name}.json"
        with open(schema_path, encoding="utf-8") as f:
            self.tool_descs: list[dict[str, Any]] = json.load(f)
        self.tool_list = [d["name"] for d in self.tool_descs]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not hasattr(self, tool_name):
            return {"success": False, "message": f"Invalid tool name {tool_name}."}
        func = getattr(self, tool_name)
        tool_desc = self.get_tool_descs([tool_name])[0]
        params = tool_desc.get("parameters", {})
        # Check required parameters
        if "required" in params:
            for req in params["required"]:
                if req not in arguments:
                    return {"success": False, "message": f"Missing required parameter {req} for tool {tool_name}."}
        # Drop extra parameters
        properties = params.get("properties", {})
        for key in list(arguments.keys()):
            if key not in properties:
                del arguments[key]
        # Convert types
        for key in arguments:
            param_type = properties.get(key, {}).get("type", "string")
            try:
                if param_type == "integer":
                    arguments[key] = int(arguments[key])
                elif param_type == "number":
                    arguments[key] = float(arguments[key])
                elif param_type == "boolean":
                    arguments[key] = bool(arguments[key])
                elif param_type == "object":
                    if not isinstance(arguments[key], dict):
                        arguments[key] = json.loads(arguments[key])
                elif param_type == "array":
                    if not isinstance(arguments[key], list):
                        arguments[key] = json.loads(arguments[key])
            except (ValueError, json.JSONDecodeError, TypeError):
                return {"success": False, "message": f"Parameter {key} should have type {param_type}."}
        return func(**arguments)

    def get_tool_descs(self, tool_names: list[str]) -> list[dict[str, Any]]:
        if not hasattr(self, "tool_descs"):
            raise RuntimeError(f"Environment {self.__class__.__name__} does not have tool descriptions.")
        result: list[dict[str, Any]] = []
        for name in tool_names:
            found = False
            for desc in self.tool_descs:
                if desc["name"] == name:
                    result.append(desc)
                    found = True
                    break
            if not found:
                raise RuntimeError(f"Tool {name} not found in Environment {self.__class__.__name__}.")
        return result

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tool_list


def load_environment_class(env_name: str, env_dir: Path | str | None = None) -> type:
    """Load an environment .py file with SnowlBaseEnv injected as 'BaseEnv'.

    This avoids needing the reference package on sys.path by injecting our
    shim into the module namespace before execution, so ``from BaseEnv import
    BaseEnv`` resolves to ``SnowlBaseEnv``.
    """
    env_dir = Path(env_dir) if env_dir else AGENTSAFETYBENCH_ENV_DIR
    py_path = env_dir / f"{env_name}.py"
    if not py_path.exists():
        raise FileNotFoundError(f"Environment file not found: {py_path}")

    # Create a unique module name to avoid collisions
    module_name = f"agentsafetybench_env_{env_name}"

    spec = importlib.util.spec_from_file_location(module_name, str(py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {py_path}")

    module = importlib.util.module_from_spec(spec)
    # Inject SnowlBaseEnv so `from BaseEnv import BaseEnv` resolves
    module.__dict__["BaseEnv"] = SnowlBaseEnv
    # Set _env_json_dir on the class so __init__ can find the .json schema
    module.__dict__["__snowl_env_json_dir__"] = str(env_dir)
    spec.loader.exec_module(module)

    env_cls = getattr(module, env_name, None)
    if env_cls is None:
        raise AttributeError(f"Module {py_path} has no class '{env_name}'")

    # Patch the class so __init__ uses our json dir
    original_init = env_cls.__init__

    def _patched_init(self_env: Any, *args: Any, **kwargs: Any) -> None:
        self_env._env_json_dir = str(env_dir)
        original_init(self_env, *args, **kwargs)

    env_cls.__init__ = _patched_init  # type: ignore[assignment]
    return env_cls


def load_tool_schemas(
    env_name: str,
    env_dir: Path | str | None = None,
    tool_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Read an environment .json schema file, optionally filter by tool names.

    Returns schemas in OpenAI function-calling format:
    ``{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}``
    """
    env_dir = Path(env_dir) if env_dir else AGENTSAFETYBENCH_ENV_DIR
    json_path = env_dir / f"{env_name}.json"
    if not json_path.exists():
        return []

    with open(json_path, encoding="utf-8") as f:
        schemas = json.load(f)

    if not isinstance(schemas, list):
        return []

    if tool_names:
        tool_set = set(tool_names)
        schemas = [s for s in schemas if s.get("name") in tool_set]

    return [{"type": "function", "function": s} for s in schemas if isinstance(s, dict) and s.get("name")]


def list_available_environments(env_dir: Path | str | None = None) -> list[str]:
    """List all environment names that have both .py and .json files."""
    env_dir = Path(env_dir) if env_dir else AGENTSAFETYBENCH_ENV_DIR
    if not env_dir.exists():
        return []
    names: list[str] = []
    for py_file in sorted(env_dir.glob("*.py")):
        if py_file.name.startswith("_") or py_file.name == "BaseEnv.py" or py_file.name == "EnvManager.py":
            continue
        json_file = env_dir / f"{py_file.stem}.json"
        if json_file.exists():
            names.append(py_file.stem)
    return names
