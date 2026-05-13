# Next Round Tasks: Iteration 3 — ToolMiddleware Protocol + ReActAgent Integration

**Predecessors**: Iteration 1 (AsyncScorer) ✓, Iteration 2 (BenchmarkConcurrencyProfile) ✓
**Unblocks**: Iteration 4 (EmulatedToolWrapper), Iteration 5 (StatefulToolExecutor), Iteration 6 (InjectionMiddleware)
**Estimated effort**: 2-3 days

---

## Task 3.1: Create ToolMiddleware Protocol and MiddlewareChain

**File**: `snowl/tools/middleware.py` (NEW)

**What to implement**:

```python
class ToolMiddleware(Protocol):
    """Intercepts and optionally transforms tool calls and their results."""
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """Pre-process tool call arguments. Return modified args."""
        return args

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """Post-process tool call result. Return modified result."""
        return result
```

**MiddlewareChain**:
- `__init__(middlewares: list[ToolMiddleware] | None = None)`
- `async def run_call(self, tool_name: str, args: dict) -> dict` — forward pass through all middlewares
- `async def run_result(self, tool_name: str, args: dict, result: Any) -> Any` — **reversed** pass through all middlewares (last middleware's intercept_result runs first on the result)
- Empty chain or `None` middlewares list = identity (no transformation)

**Built-in middlewares** (in the same file):
- `LoggingMiddleware`: records all tool calls and results in `self.log` list for inspection
- `IdentityMiddleware`: no-op, useful for testing composition

**Tests** (`tests/test_tool_middleware.py`):
- MiddlewareChain with empty list returns args/result unchanged
- MiddlewareChain with single middleware: call and result are intercepted
- MiddlewareChain ordering: calls go forward (M1 -> M2), results go backward (M2 -> M1)
- LoggingMiddleware captures all calls with tool_name, args, result
- IdentityMiddleware is transparent

---

## Task 3.2: Add async_callable to ToolSpec and execute() method

**File**: `snowl/core/tool.py` (modify)

**Changes**:
1. Add `async_callable: Callable[..., Awaitable[Any]] | None = None` field to `ToolSpec`
2. Add `async def execute(self, **kwargs) -> Any` method:
   - If `async_callable` is not None: `return await self.async_callable(**kwargs)`
   - If `callable` is not None: call it; if result is awaitable, `return await result`; else return result
   - If both None: raise RuntimeError

**Note**: The current `ReActAgent._execute_tool_call` already handles `hasattr(result, "__await__")` (line 471-473). The `execute()` method provides a cleaner, unified API.

**Tests** (update `tests/test_agent_contracts.py`):
- ToolSpec with sync callable: `execute()` returns result
- ToolSpec with async callable: `execute()` awaits and returns result
- ToolSpec with both: `execute()` prefers async_callable
- ToolSpec with neither: `execute()` raises RuntimeError

---

## Task 3.3: Wire MiddlewareChain into ReActAgent

**File**: `snowl/agents/react_agent.py` (modify)

**Changes**:

1. Add field to `ReActAgent` dataclass (after line 72):
   ```python
   middlewares: list[Any] | None = None
   ```

2. In `run()` method: build `MiddlewareChain` from `self.middlewares`:
   ```python
   from snowl.tools.middleware import MiddlewareChain
   middleware_chain = MiddlewareChain(self.middlewares)
   ```
   Pass `middleware_chain` through to `_execute_tool_call`.

3. Modify `_execute_tool_call` (line 450-474):
   ```python
   async def _execute_tool_call(self, tool_name, raw_arguments, tool_map, allowed_tool_names, middleware_chain=None):
       if tool_name not in allowed_tool_names:
           return f"ERROR: unknown tool '{tool_name}'"

       tool_fn = tool_map.get(tool_name)
       if tool_fn is None:
           return f"Tool '{tool_name}' not found."

       try:
           parsed_args = json.loads(raw_arguments or "{}")
           if not isinstance(parsed_args, dict):
               parsed_args = {}
       except json.JSONDecodeError:
           parsed_args = {}

       # Run middleware intercept_call
       if middleware_chain is not None:
           parsed_args = await middleware_chain.run_call(tool_name, parsed_args)

       result = tool_fn(**parsed_args)
       if hasattr(result, "__await__"):
           result = await result

       # Run middleware intercept_result
       if middleware_chain is not None:
           result = await middleware_chain.run_result(tool_name, parsed_args, result)

       return result
   ```

**Key principle**: Middleware is only invoked for known, allowed tools. Unknown tool names return the error message before middleware runs.

**Tests** (`tests/test_react_agent_middleware.py`):
- ReActAgent with `middlewares=None` produces identical output to before
- ReActAgent with `middlewares=[]` (empty list) produces identical output
- ReActAgent with `LoggingMiddleware`: tool calls are logged, results are unchanged
- Middleware can modify args before execution (e.g., add a default parameter)
- Middleware can modify result after execution (e.g., truncate, inject)
- Multiple middlewares compose correctly (call order M1->M2, result order M2->M1)
- Unknown tool still returns error; middleware not invoked

---

## Task 3.4: Write documentation

**Create**: `docs/tool_middleware.md` (EN) — document the ToolMiddleware protocol, how to write custom middleware, MiddlewareChain composition, and integration with ReActAgent

**Update**: `README.md` — add "Tool Middleware" subsection under the architecture section

**Update**: `ARCHITECTURE.md` — add middleware to the agent execution pipeline description

---

## Task 3.5: Write progress file

**File**: `refactor_plan/progress/03_tool_middleware.md`

Contents: what was completed, test results, deviations, known issues, next iteration recommendation.

---

## Verification Checklist

1. `pytest tests/ -q` — all tests pass
2. Existing eval (e.g., `examples/strongreject-official`) produces identical output with no middleware
3. `LoggingMiddleware` captures tool calls without affecting results
4. `_execute_tool_call` still handles unknown tools correctly (middleware not invoked)

---

## Key Files Reference

| File | Action | Key Lines |
|------|--------|-----------|
| `snowl/tools/middleware.py` | NEW | Entire file |
| `snowl/core/tool.py` | MODIFY | `ToolSpec` dataclass |
| `snowl/agents/react_agent.py` | MODIFY | Line 62 (add field), line 74-80 (build chain), line 450-474 (wire chain) |
| `tests/test_tool_middleware.py` | NEW | Entire file |
| `tests/test_react_agent_middleware.py` | NEW | Entire file |
| `tests/test_agent_contracts.py` | UPDATE | Add ToolSpec.execute tests |
| `docs/tool_middleware.md` | NEW | Entire file |
