# Writing an Agent

An agent is any Python object that satisfies the `Agent` protocol:

- `agent_id: str` — unique identifier
- `async def run(self, state, context, tools=None) -> AgentState` — execution loop

---

## Minimal agent

```python
from snowl.core import agent as declare_agent, AgentState, AgentContext

class MyAgent:
    agent_id = "my_agent"

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        state.output = {"message": "Hello from my agent!"}
        state.stop_reason = "completed"
        return state

@declare_agent(agent_id="my_agent")
def agents():
    return [MyAgent()]
```

## ReAct agent with tools

The built-in `ReActAgent` runs a Plan-Act-Observe loop with LLM-powered tool
calling:

```python
from pathlib import Path
from snowl.agents import ReActAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, ProjectModelEntry, ProjectProviderConfig

PROJECT_DIR = Path(__file__).resolve().parent

def _build_react_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig):
    client = OpenAICompatibleChatClient(model_entry.config)
    return ReActAgent(
        model_client=client,
        agent_id="react_agent",
        max_steps=10,
    )

@declare_agent(agent_id="react_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="react_agent",
        factory=_build_react_agent,
    )
```

### ReActAgent parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_client` | `OpenAICompatibleChatClient` | required | LLM client for generating responses |
| `agent_id` | `str` | `"react_agent"` | Unique agent identifier |
| `max_steps` | `int` | `8` | Maximum reasoning/tool-calling steps |
| `temperature` | `float` | `0.2` | LLM sampling temperature |
| `middlewares` | `list \| None` | `None` | Tool middleware chain |
| `enable_json_fallback` | `bool` | `True` | Fallback to JSON parsing for tool calls |
| `native_tool_call_policy` | `str` | `"single"` | How to handle native tool calls |

## Chat agent (single-shot)

The built-in `ChatAgent` sends one LLM call and returns:

```python
from snowl.agents import ChatAgent

agent = ChatAgent(
    model_client=client,
    agent_id="chat_agent",
)
```

## Agent with ToolMiddleware

Inject middleware to intercept tool calls:

```python
from snowl.tools.middleware import LoggingMiddleware
from snowl.agents import ReActAgent

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
    max_steps=8,
)
```

See [Tool Middleware](tool-middleware.md) for full details.

## AgentState fields

The `AgentState` object carries the agent's execution state:

| Field | Type | Purpose |
|-------|------|---------|
| `messages` | `list[dict]` | Conversation history |
| `actions` | `list[Action]` | Tool calls made |
| `observations` | `list[Observation]` | Tool results received |
| `output` | `dict \| None` | Final output payload |
| `stop_reason` | `StopReason \| None` | Why the agent stopped |

### StopReason values

| Value | Meaning |
|-------|---------|
| `COMPLETED` | Agent finished successfully |
| `MAX_STEPS` | Reached maximum step count |
| `LIMIT_EXCEEDED` | Exceeded a resource limit |
| `ERROR` | Agent encountered an error |
| `CANCELLED` | Agent was cancelled |

## AgentContext fields

The `AgentContext` object provides trial metadata:

| Field | Type | Purpose |
|-------|------|---------|
| `task_id` | `str` | Task identifier |
| `sample_id` | `str \| None` | Sample identifier |
| `metadata` | `dict` | Sample metadata from the benchmark adapter |

## Multi-model sweeps

Use `build_model_variants` to evaluate the same agent logic across multiple
models defined in `project.yml`:

```python
@declare_agent(agent_id="react_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="react_agent",
        factory=_build_react_agent,
    )
```

Snowl creates one `AgentVariant` per model in `agent_matrix.models` and plans
trials for every (task × variant × sample) combination.

## Custom agent patterns

### Wrapping an external framework

```python
class LangGraphWrapper:
    agent_id = "langgraph_agent"

    def __init__(self, graph, client):
        self.graph = graph
        self.client = client

    async def run(self, state, context, tools=None):
        result = await self.graph.ainvoke({"messages": state.messages})
        state.output = result
        state.stop_reason = "completed"
        return state
```

### Accessing sample metadata

```python
class ContextAwareAgent:
    agent_id = "context_aware"

    async def run(self, state, context, tools=None):
        suite = context.metadata.get("suite", "unknown")
        # Use suite-specific logic
        ...
```
