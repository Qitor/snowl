"""GUI tool adapter that maps high-level GUI actions to normalized `ToolSpec` callables.

Framework role:
- Wraps `GuiEnv.execute_action` primitives with stable tool names and required-op declarations.
- Provides backward-compatible aliases (`key`, `terminate`) used by existing prompts/agents.

Runtime/usage wiring:
- Runtime injects these tool specs into agent context for GUI-capable tasks.

Change guardrails:
- Tool name/argument changes are prompt-breaking; keep compatibility unless migration is coordinated.
"""

from __future__ import annotations

from dataclasses import dataclass

from snowl.core import ToolSpec, build_tool_spec
from snowl.envs import GuiEnv


@dataclass
class GuiToolset:
    env: GuiEnv | None = None

    def _exec(self, action: dict) -> dict:
        if self.env is None:
            return {"simulated": True, "action": action}
        return self.env.execute_action(action)


    def move_to(self, x: float, y: float, duration: float = 0.0) -> dict:
        """Move mouse to coordinates."""
        return self._exec({"action_type": "MOVE_TO", "parameters": {"x": x, "y": y, "duration": duration}})

    def mouse_move(self, x: float, y: float, duration: float = 0.0) -> dict:
        """Alias for move_to."""
        return self._exec({"action_type": "MOUSE_MOVE", "parameters": {"x": x, "y": y, "duration": duration}})

    def click(self, x: float, y: float, button: str = "left", num_clicks: int = 1) -> dict:
        """Click at coordinates."""
        return self._exec({"action_type": "CLICK", "parameters": {"x": x, "y": y, "button": button, "num_clicks": int(num_clicks)}})

    def right_click(self, x: float, y: float) -> dict:
        """Right click at coordinates."""
        return self._exec({"action_type": "RIGHT_CLICK", "parameters": {"x": x, "y": y}})

    def double_click(self, x: float, y: float) -> dict:
        """Double click at coordinates."""
        return self._exec({"action_type": "DOUBLE_CLICK", "parameters": {"x": x, "y": y}})

    def mouse_down(self, button: str = "left") -> dict:
        """Mouse button down."""
        return self._exec({"action_type": "MOUSE_DOWN", "parameters": {"button": button}})

    def mouse_up(self, button: str = "left") -> dict:
        """Mouse button up."""
        return self._exec({"action_type": "MOUSE_UP", "parameters": {"button": button}})

    def drag_to(self, x: float, y: float, duration: float = 1.0, button: str = "left") -> dict:
        """Drag mouse to coordinates."""
        return self._exec({"action_type": "DRAG_TO", "parameters": {"x": x, "y": y, "duration": duration, "button": button}})

    def scroll(self, dx: int = 0, dy: int = -800) -> dict:
        """Scroll wheel."""
        return self._exec({"action_type": "SCROLL", "parameters": {"dx": int(dx), "dy": int(dy)}})

    def type_text(self, text: str) -> dict:
        """Type text."""
        return self._exec({"action_type": "TYPING", "parameters": {"text": text}})

    def press(self, key: str) -> dict:
        """Press a key."""
        return self._exec({"action_type": "PRESS", "parameters": {"key": key}})

    def key(self, key: str) -> dict:
        """Backward-compatible alias for press."""
        return self.press(key)

    def key_down(self, key: str) -> dict:
        """Key down."""
        return self._exec({"action_type": "KEY_DOWN", "parameters": {"key": key}})

    def key_up(self, key: str) -> dict:
        """Key up."""
        return self._exec({"action_type": "KEY_UP", "parameters": {"key": key}})

    def hotkey(self, keys: list[str]) -> dict:
        """Press hotkey combination."""
        return self._exec({"action_type": "HOTKEY", "parameters": {"keys": keys}})

    def wait(self, seconds: float = 1.0) -> dict:
        """Wait for UI updates."""
        return self._exec({"action_type": "WAIT", "parameters": {"time": float(seconds)}})

    def done(self, status: str = "success") -> dict:
        """Mark task as done."""
        return self._exec({"action_type": "DONE", "parameters": {"status": status}})

    def fail(self, reason: str = "") -> dict:
        """Mark task as failed."""
        return self._exec({"action_type": "FAIL", "parameters": {"reason": reason}})

    def terminate(self, status: str = "success") -> dict:
        """Backward-compatible terminate action."""
        if str(status).lower() in {"success", "done", "completed"}:
            return self.done(status=status)
        return self.fail(reason=str(status))


def build_gui_tools(env: GuiEnv | None = None) -> list[ToolSpec]:
    bundle = GuiToolset(env=env)
    return [
        build_tool_spec(bundle.click, name="gui_click", description="Click on GUI coordinates.", required_ops=["gui.click", "gui.action"]),
        build_tool_spec(bundle.type_text, name="gui_type", description="Type text into focused GUI input.", required_ops=["gui.type", "gui.action"]),
        build_tool_spec(bundle.key, name="gui_key", description="Press GUI key.", required_ops=["gui.key", "gui.action"]),
        build_tool_spec(bundle.scroll, name="gui_scroll", description="Scroll GUI viewport.", required_ops=["gui.scroll", "gui.action"]),
        build_tool_spec(bundle.wait, name="gui_wait", description="Wait for GUI state updates.", required_ops=["gui.wait", "gui.action"]),
        build_tool_spec(bundle.terminate, name="gui_terminate", description="Terminate GUI task.", required_ops=["gui.terminate", "gui.action"]),
    ]

