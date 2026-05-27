"""Shared sync/async bridge for running coroutines from synchronous scorer contexts.

Framework role:
- Provides `run_coro_sync()` to execute async coroutines from sync `.score()` methods.
- Handles the case where an event loop is already running (e.g., in Jupyter) by
  spawning a daemon thread.

Runtime/usage wiring:
- Used by ModelAsJudgeJSONScorer and RegexGradeJudgeScorer to call async model
  clients from their synchronous `score()` methods.

Change guardrails:
- This is a shared utility; do not add scorer-specific logic here.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any


def run_coro_sync(coro: Any) -> Any:
    """Run an async coroutine from a synchronous context.

    If no event loop is running, uses ``asyncio.run()`` directly.
    If an event loop is already running (e.g., inside Jupyter), spawns a daemon
    thread to avoid "cannot run the event loop while another loop is running".
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_box["result"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive
            error_box["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("result")
