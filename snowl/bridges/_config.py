"""Bridge configuration and ContextVar management.

Framework role:
- Defines BridgeConfig dataclass and the ContextVar that controls whether
  bridge patches are active for the current coroutine.
- No third-party imports; bridge patches import this module.

Runtime/usage wiring:
- The ContextVar is set by ``snowl_bridge()`` context manager and checked
  by every patched SDK method on each call.

Change guardrails:
- Keep this module dependency-free (no openai/anthropic imports) so patches
  can import it without circular dependency issues.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class BridgeConfig:
    """Active bridge configuration, stored in a ContextVar."""

    enabled: bool = False
    model_client: Any | None = None  # ChatModelClient (duck-typed, no import)
    on_call: Callable[[dict[str, Any]], None] | None = None
    provider_id: str = "default"


@dataclass
class BridgeUsageAccumulator:
    """Accumulates model call usage within a bridge session."""

    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_timings_ms: list[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_timings_ms is None:
            self.call_timings_ms = []


# ContextVar that controls whether patches redirect calls.
# When None or not enabled, patches pass through to the original method.
_bridge_config: ContextVar[BridgeConfig | None] = ContextVar(
    "snowl_bridge_config", default=None
)

# ContextVar that holds the usage accumulator for the current bridge session.
_usage_accumulator: ContextVar[BridgeUsageAccumulator | None] = ContextVar(
    "snowl_bridge_usage", default=None
)


def get_bridge_config() -> BridgeConfig | None:
    """Return the active bridge config for the current coroutine."""
    return _bridge_config.get()


def set_bridge_config(config: BridgeConfig | None) -> Any:
    """Set the bridge config and return the token for reset."""
    return _bridge_config.set(config)


def reset_bridge_config(token: Any) -> None:
    """Reset the bridge config using a previously returned token."""
    _bridge_config.reset(token)


def get_usage_accumulator() -> BridgeUsageAccumulator | None:
    """Return the usage accumulator for the current bridge session."""
    return _usage_accumulator.get()


def set_usage_accumulator(acc: BridgeUsageAccumulator | None) -> Any:
    """Set the usage accumulator and return the token for reset."""
    return _usage_accumulator.set(acc)


def reset_usage_accumulator(token: Any) -> None:
    """Reset the usage accumulator using a previously returned token."""
    _usage_accumulator.reset(token)


def record_model_call(
    *,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    duration_ms: int,
    model: str | None = None,
) -> None:
    """Record a model call into the current usage accumulator."""
    acc = get_usage_accumulator()
    if acc is None:
        return
    acc.call_count += 1
    acc.input_tokens += input_tokens
    acc.output_tokens += output_tokens
    acc.total_tokens += total_tokens
    acc.call_timings_ms.append(duration_ms)
