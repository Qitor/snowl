from __future__ import annotations

from snowl.core import tool


@tool(required_ops=["gui.click", "gui.action"])
def gui_click(x: float, y: float, button: str = "left", num_clicks: int = 1) -> str:
    """Click at given coordinates."""
    return f"click({x},{y},{button},{num_clicks})"


@tool(required_ops=["gui.type", "gui.action"])
def gui_type(text: str) -> str:
    """Type text into focused field."""
    return f"type({text})"


@tool(required_ops=["gui.key", "gui.action"])
def gui_key(key: str) -> str:
    """Press a key."""
    return f"key({key})"


@tool(required_ops=["gui.scroll", "gui.action"])
def gui_scroll(dx: int = 0, dy: int = -800) -> str:
    """Scroll GUI viewport."""
    return f"scroll({dx},{dy})"


@tool(required_ops=["gui.wait", "gui.action"])
def gui_wait(seconds: float = 1.0) -> str:
    """Wait for UI updates."""
    return f"wait({seconds})"


@tool(required_ops=["gui.terminate", "gui.action"])
def gui_terminate(status: str = "success") -> str:
    """Terminate task execution."""
    return f"terminate({status})"

