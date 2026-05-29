# How to Create a Framework Adapter

This guide explains how to create and register a new framework adapter so that agents from any Python framework can be evaluated with Snowl.

## Overview

A **framework adapter** bridges between an external agent framework (LangGraph, QitOS, OpenAI Agents SDK, etc.) and Snowl's `Agent` protocol. The adapter wraps a framework-specific agent into a Snowl-compatible `Agent` that the evaluation runtime can execute.

## Quick Start

### Option A: Cookiecutter template (Recommended)

Use the cookiecutter template to generate a complete adapter package:

```bash
pip install cookiecutter
cookiecutter templates/cookiecutter-snowl-adapter/
```

This generates:
- `{{module_name}}/adapter.py` — adapter implementation
- `{{module_name}}/__init__.py` — package exports
- `tests/test_adapter.py` — basic conformance tests
- `pyproject.toml` — with entry_points declaration

### Option B: Manual setup

### 1. Copy the template

```bash
cp templates/adapter/adapter.py snowl/adapters/your_framework.py
```

### 2. Implement the adapter

Replace all `{{...}}` placeholders in the template:

- `{{FrameworkName}}` — PascalCase class name (e.g., `CrewAI`)
- `{{framework_name}}` — kebab-case identifier (e.g., `crewai`)

You must implement:

```python
class YourFrameworkAdapter(BaseFrameworkAdapter):
    @property
    def framework_name(self) -> str:
        return "your_framework"

    def wrap(self, agent, **kwargs):
        """Wrap a framework agent as a Snowl Agent."""
        return _YourFrameworkAgent(agent=agent, config=kwargs)
```

The inner `_YourFrameworkAgent` class must implement the Agent protocol:

```python
class _YourFrameworkAgent:
    agent_id: str

    async def run(self, state, context, tools=None) -> AgentState:
        # 1. Extract instruction from state.messages
        # 2. Call framework agent
        # 3. Return updated AgentState
```

### 3. Handle optional dependencies

If the framework is an optional dependency, add a lazy import check:

```python
def _check_your_framework_available() -> None:
    try:
        importlib.import_module("your_framework")
    except ImportError as exc:
        raise ImportError(
            "The 'your_framework' package is required. "
            "Install it with: pip install your_framework"
        ) from exc
```

Call it in `wrap()` so Snowl can be imported without the framework installed.

### 4. Register the adapter

In `snowl/adapters/registry.py`:

```python
from snowl.adapters.your_framework import YourFrameworkAdapter
_default_registry.register("your_framework", YourFrameworkAdapter)
```

### 5. Declare entry point

In `pyproject.toml`:

```toml
[project.entry-points."snowl.adapters"]
your_framework = "snowl.adapters.your_framework:YourFrameworkAdapter"
```

### 6. Use in project.yml

```yaml
eval:
  framework: your_framework
```

## Optional Methods

### `unwrap_state(snowl_state) -> Any`

Convert Snowl `AgentState` to a framework-native task/context. Override when the framework has its own task representation.

### `wrap_result(framework_result, snowl_state) -> AgentState`

Convert a framework result object back to an updated `AgentState`. Override when the framework returns a structured result (e.g., `EngineResult`).

### `wrap_tools(snowl_tools) -> list`

Convert Snowl `ToolSpec` objects to framework-native tools. Override for tool interop.

## Testing

Create `tests/test_your_framework_adapter.py`:

```python
from snowl.adapters.your_framework import YourFrameworkAdapter
from snowl.core.agent import AgentState, StopReason

def test_framework_name():
    adapter = YourFrameworkAdapter()
    assert adapter.framework_name == "your_framework"

@pytest.mark.asyncio
async def test_wrap_and_run():
    adapter = YourFrameworkAdapter()
    # Use a mock framework agent
    agent = adapter.wrap(mock_agent)
    state = AgentState(messages=[{"role": "user", "content": "Hello"}])
    result = await agent.run(state, context=None)
    assert isinstance(result, AgentState)
```

## Existing Adapters

| Adapter | File | Framework |
|---------|------|-----------|
| `custom` | `snowl/adapters/custom.py` | Bare async functions |
| `langgraph` | `snowl/adapters/langgraph.py` | LangGraph compiled graphs |
| `openai_agents` | `snowl/adapters/openai_agents.py` | OpenAI Agents SDK |
| `qitos` | `snowl/adapters/qitos.py` | QitOS AgentModule |

## Community Adapters

Third-party adapters can be published as separate packages using the `snowl.adapters.contrib` namespace. The adapter's `pyproject.toml` should declare an entry point:

```toml
[project.entry-points."snowl.adapters"]
your_framework = "snowl.adapters.contrib.your_framework:YourFrameworkAdapter"
```

Snowl's adapter registry auto-discovers entry points from the `snowl.adapters` group, so no changes to Snowl itself are needed.
