# Tool Middleware

ToolMiddleware is a protocol for intercepting and optionally transforming tool calls and their results within the Snowl agent execution pipeline. It enables composable plugins for tool emulation, stateful execution, injection testing, and logging.

## ToolMiddleware Protocol

```python
class ToolMiddleware(Protocol):
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
```

- `intercept_call`: Receives the tool name and parsed arguments dict before execution. Must return a dict (modified or unchanged).
- `intercept_result`: Receives the tool name, arguments, and the tool's return value after execution. May return a transformed result.

## MiddlewareChain

`MiddlewareChain` composes multiple middlewares with defined ordering:

- **Calls flow forward**: M1.intercept_call → M2.intercept_call → ... → tool execution
- **Results flow backward**: ... → M2.intercept_result → M1.intercept_result

An empty chain or `None` middlewares list is identity (no transformation).

```python
from snowl.tools.middleware import MiddlewareChain

chain = MiddlewareChain([middleware_a, middleware_b])
args = await chain.run_call("tool_name", {"arg": "value"})
# ... tool execution ...
result = await chain.run_result("tool_name", args, raw_result)
```

## Integration with ReActAgent

Pass a list of middlewares to `ReActAgent` to enable interception:

```python
from snowl.agents.react_agent import ReActAgent
from snowl.tools.middleware import LoggingMiddleware

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
)
```

Key behavior:
- Middleware is only invoked for known, allowed tools. Unknown tool names return an error message before middleware runs.
- When `middlewares` is `None` or empty, behavior is identical to the original agent (no interception).

## Writing Custom Middleware

Implement the `ToolMiddleware` protocol:

```python
class TruncateResultMiddleware:
    """Truncates string results to a maximum length."""

    def __init__(self, max_length: int = 100):
        self.max_length = max_length

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args  # no modification to args

    async def intercept_result(self, tool_name: str, args: dict, result) -> Any:
        if isinstance(result, str) and len(result) > self.max_length:
            return result[:self.max_length] + "..."
        return result
```

## Built-in Middlewares

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

## ToolSpec.execute()

`ToolSpec` now supports an `async_callable` field and an `execute()` method:

```python
# Sync callable (existing)
spec = ToolSpec(name="add", description="Add", parameters={...}, callable=add_fn)
result = await spec.execute(a=1, b=2)

# Async callable (new)
spec = ToolSpec(name="fetch", description="Fetch", parameters={...},
                callable=lambda: None, async_callable=async_fetch_fn)
result = await spec.execute(url="https://example.com")
```

When both `callable` and `async_callable` are set, `async_callable` takes precedence.
