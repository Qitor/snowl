"""Hooks protocol and registry for eval lifecycle callbacks.

Framework role:
- Defines ``TrialHooks`` protocol with lifecycle callbacks for eval runs.
- Provides ``@hooks`` decorator for declarative hook registration.
- ``HooksBridge`` translates RunEventBus events into hook method calls.

Runtime/usage wiring:
- Hooks are discovered alongside agents/scorers during autodiscovery.
- HooksBridge subscribes to RunEventBus events and dispatches to registered hooks.
- Hook errors are isolated — they never crash the main eval loop.

Change guardrails:
- Must only import from ``snowl.core``; no runtime/engine dependencies.
- Hook methods are all async and optional — partial implementation is fine.
- Keep the hook surface small; niche needs should use RunEventBus directly.

Reference:
- ``references/inspect_ai/src/inspect_ai/hooks/_hooks.py`` (Inspect AI Hooks)
- ``references/harbor/src/harbor/trial/hooks.py`` (Harbor TrialHookEvent)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from snowl.core.declarations import declare
from snowl.errors import SnowlValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook context types
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """Context passed to on_run_start / on_run_end hooks."""
    run_id: str
    benchmark: str
    experiment_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrialContext:
    """Context passed to per-trial hook callbacks."""
    task_id: str
    agent_id: str
    variant_id: str
    sample_id: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TrialHooks Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class TrialHooks(Protocol):
    """Eval lifecycle hook protocol.

    Implement any subset of these methods. All methods are async and optional.
    Unimplemented methods are simply not called.

    Reference: ``references/inspect_ai/src/inspect_ai/hooks/_hooks.py``
    """

    hooks_id: str

    async def on_run_start(self, context: RunContext) -> None:
        """Called when the entire eval run starts."""
        ...

    async def on_run_end(self, context: RunContext, results: list[Any]) -> None:
        """Called when the entire eval run ends."""
        ...

    async def on_trial_start(self, context: TrialContext) -> None:
        """Called when a single trial starts."""
        ...

    async def on_trial_end(self, context: TrialContext, result: Any) -> None:
        """Called when a single trial ends."""
        ...

    async def on_model_usage(self, context: TrialContext, usage: dict[str, Any]) -> None:
        """Called after a model API call with usage stats."""
        ...

    async def on_score(self, context: TrialContext, scores: dict[str, Any]) -> None:
        """Called after scoring completes."""
        ...

    async def on_error(self, context: TrialContext, error: Exception) -> None:
        """Called when a trial encounters an error."""
        ...


# ---------------------------------------------------------------------------
# @hooks decorator
# ---------------------------------------------------------------------------

def hooks(
    value: Any | None = None,
    *,
    hooks_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Declare a hooks object/factory for eval autodiscovery."""

    if hooks_id is not None and (not isinstance(hooks_id, str) or not hooks_id.strip()):
        raise SnowlValidationError("Decorator @hooks(...): 'hooks_id' must be a non-empty string.")

    def _decorate(inner: Any) -> Any:
        declared_id = hooks_id.strip() if isinstance(hooks_id, str) and hooks_id.strip() else None
        if declared_id is not None and hasattr(inner, "hooks_id"):
            try:
                setattr(inner, "hooks_id", declared_id)
            except Exception:
                pass
        return declare(inner, kind="hooks", object_id=declared_id, metadata=metadata)

    if value is not None:
        return _decorate(value)
    return _decorate


# ---------------------------------------------------------------------------
# HooksBridge — translates events to hook calls
# ---------------------------------------------------------------------------

class HooksBridge:
    """Bridge RunEventBus events to registered TrialHooks.

    Listens to events from the eval loop and dispatches them to
    the appropriate hook methods. All hook calls are error-isolated.
    """

    def __init__(self, hooks_list: list[Any]) -> None:
        self._hooks = hooks_list

    async def dispatch(self, event_name: str, **kwargs: Any) -> None:
        """Dispatch an event to all registered hooks.

        Each hook call is wrapped in try/except so that a failing
        hook never crashes the main eval loop.
        """
        method_name = _event_to_method(event_name)
        if method_name is None:
            return

        for hook in self._hooks:
            method = getattr(hook, method_name, None)
            if method is None or not callable(method):
                continue
            try:
                await method(**kwargs)
            except Exception as exc:
                hid = getattr(hook, "hooks_id", type(hook).__name__)
                logger.warning("Hook %s.%s failed: %s", hid, method_name, exc)


# ---------------------------------------------------------------------------
# Event-to-method mapping
# ---------------------------------------------------------------------------

_EVENT_METHOD_MAP: dict[str, str] = {
    "run.start": "on_run_start",
    "run.end": "on_run_end",
    "trial.start": "on_trial_start",
    "trial.end": "on_trial_end",
    "trial.error": "on_error",
    "model.usage": "on_model_usage",
    "scorer.finish": "on_score",
}


def _event_to_method(event_name: str) -> str | None:
    """Map an event name to a hook method name.

    Supports both short names ('trial.start') and runtime-prefixed
    names ('runtime.trial.start').
    """
    if event_name in _EVENT_METHOD_MAP:
        return _EVENT_METHOD_MAP[event_name]
    # Try stripping 'runtime.' prefix
    if event_name.startswith("runtime."):
        short = event_name[len("runtime."):]
        if short in _EVENT_METHOD_MAP:
            return _EVENT_METHOD_MAP[short]
    return None
