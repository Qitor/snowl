# Tool Middleware

Tool middleware intercepts tool calls and results, enabling powerful patterns
like logging, emulation, and stateful execution.

---

## The ToolMiddleware protocol

```python
class ToolMiddleware(Protocol):
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
```

- `intercept_call`: Receives the tool name and parsed arguments before
  execution. Must return a dict (modified or unchanged).
- `intercept_result`: Receives the tool name, arguments, and the tool's return
  value after execution. May return a transformed result.

## MiddlewareChain

Middlewares are composed in a `MiddlewareChain`:

- **Calls flow forward**: M1.intercept_call → M2.intercept_call → tool execution
- **Results flow backward**: tool → M2.intercept_result → M1.intercept_result

```python
from snowl.tools.middleware import MiddlewareChain

chain = MiddlewareChain([middleware_a, middleware_b])
args = await chain.run_call("tool_name", {"arg": "value"})
# ... tool execution ...
result = await chain.run_result("tool_name", args, raw_result)
```

An empty chain or `None` middlewares list is identity (no transformation).

## Integration with ReActAgent

Pass a list of middlewares to `ReActAgent`:

```python
from snowl.agents import ReActAgent
from snowl.tools.middleware import LoggingMiddleware

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
)
```

Key behavior:

- Middleware is only invoked for known, allowed tools
- Unknown tool names return an error message before middleware runs
- When `middlewares` is `None` or empty, behavior is identical to no interception

## Built-in middlewares

### LoggingMiddleware

Records all tool calls and results in `self.log` for inspection:

```python
lm = LoggingMiddleware()
agent = ReActAgent(model_client=client, middlewares=[lm])
# ... run agent ...
for entry in lm.log:
    print(entry["phase"], entry["tool_name"])
```

### IdentityMiddleware

No-op middleware useful for testing composition.

### EmulatedToolWrapper

Replaces tool results with LM-emulated observations. See
[ToolEmu Emulation](../how-to/toolemu-emulation.md).

### StatefulToolExecutor

Replaces sentinel stubs with real stateful execution. See
[Stateful Tool Execution](stateful-tool-execution.md).

## Custom middleware

Implement the `ToolMiddleware` protocol:

```python
class TruncateMiddleware:
    """Truncates string results to a maximum length."""

    def __init__(self, max_length: int = 500):
        self.max_length = max_length

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args  # passthrough

    async def intercept_result(self, tool_name: str, args: dict, result) -> Any:
        if isinstance(result, str) and len(result) > self.max_length:
            return result[:self.max_length] + "... (truncated)"
        return result
```

Wire it into an agent:

```python
agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware(), TruncateMiddleware()],
)
```

## Composing multiple middlewares

Middlewares compose in order. Calls flow forward through the chain, results
flow backward:

```python
agent = ReActAgent(
    model_client=client,
    middlewares=[
        LoggingMiddleware(),        # Logs all calls and results
        TruncateMiddleware(),       # Truncates long results
        StatefulToolExecutor(...),  # Replaces sentinels with real execution
    ],
)
```

In this example:

1. `LoggingMiddleware.intercept_call` logs the call
2. `TruncateMiddleware.intercept_call` passes through
3. `StatefulToolExecutor.intercept_call` passes through
4. Tool executes
5. `StatefulToolExecutor.intercept_result` replaces sentinel with real result
6. `TruncateMiddleware.intercept_result` truncates if needed
7. `LoggingMiddleware.intercept_result` logs the result
