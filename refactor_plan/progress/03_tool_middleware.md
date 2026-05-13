# Progress: Iteration 3 — ToolMiddleware Protocol + ReActAgent Integration

**Status**: COMPLETED
**Date**: 2026-05-12

## What Was Completed

1. **`snowl/tools/middleware.py`** (NEW) — Added:
   - `ToolMiddleware` protocol with `intercept_call` and `intercept_result` async methods
   - `MiddlewareChain`: composes multiple middlewares with forward-call / reverse-result ordering
   - `LoggingMiddleware`: records all tool calls and results in `self.log` list
   - `IdentityMiddleware`: no-op middleware for testing composition

2. **`snowl/core/tool.py`** (MODIFIED) — Added:
   - `async_callable: Callable[..., Awaitable[Any]] | None = None` field on `ToolSpec`
   - `async def execute(self, **kwargs) -> Any` method: prefers async_callable, then callable (with awaitable detection), raises RuntimeError if neither

3. **`snowl/agents/react_agent.py`** (MODIFIED) — Added:
   - `middlewares: list[Any] | None = None` field on `ReActAgent`
   - `MiddlewareChain` import and construction in `run()` method
   - `middleware_chain` parameter on `_execute_tool_call`
   - `chain.run_call()` before tool execution, `chain.run_result()` after tool execution
   - Both call sites (JSON fallback and native tool calling) pass middleware_chain

4. **`tests/test_tool_middleware.py`** (NEW) — 15 tests:
   - Empty chain / None middlewares: identity
   - Single middleware: call and result interception
   - Call order forward (M1->M2), result order reversed (M2->M1)
   - LoggingMiddleware: captures calls, results, does not modify values
   - IdentityMiddleware: transparent
   - Protocol compliance checks

5. **`tests/test_react_agent_middleware.py`** (NEW) — 8 tests:
   - Agent with `middlewares=None` and `middlewares=[]`: backward compat
   - LoggingMiddleware captures tool calls without affecting results
   - Middleware modifies args (add default parameter)
   - Middleware modifies result (transform output)
   - Multiple middlewares compose correctly (forward/reverse order)
   - Unknown tool returns error without invoking middleware
   - `_execute_tool_call` without chain (backward compat)

6. **`tests/test_agent_contracts.py`** (UPDATED) — 5 new tests:
   - ToolSpec.execute with sync callable
   - ToolSpec.execute with async callable
   - ToolSpec.execute prefers async_callable over callable
   - ToolSpec.execute handles sync callable returning awaitable
   - ToolSpec.execute raises RuntimeError without callable

7. **`docs/tool_middleware.md`** (NEW) — Full documentation of protocol, chain, integration, custom middleware, built-ins, ToolSpec.execute

8. **`README.md`** (UPDATED) — Added "Tool Middleware" subsection in Core Contract section; added `ToolMiddleware` to internal architecture boundaries list

9. **`ARCHITECTURE.md`** (UPDATED) — Added middleware pipeline description in section 3.3

## Test Results

- 397 passed, 1 skipped (no regressions)
- 28 new tests (15 middleware + 8 agent integration + 5 ToolSpec.execute)

## Deviations from Plan

- None. All planned changes implemented as specified.

## Known Issues / Follow-up Items

- The `MiddlewareChain` is constructed fresh in each `run()` call. For long-running agents with many tool calls, this is fine. If stateful middlewares need to persist across agent runs, they should be passed as the same instance.
- `ToolSpec.async_callable` is optional and defaults to `None`. The `build_tool_spec()` helper does not auto-detect async functions — users must explicitly set `async_callable` when constructing ToolSpec directly. This is intentional: the existing `callable` field handles both sync and async-returning functions via `hasattr(result, "__await__")` in `_execute_tool_call`, and the new `async_callable` is for the cleaner `execute()` API path.

## Next Iteration

**Iteration 4: EmulatedToolWrapper — ToolEmu LM Emulation** — Implement ToolEmu's LM-emulated sandbox as a ToolMiddleware.
