"""Built-in GUI tools for OSWorld-like tasks."""

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

    def click(self, x: float, y: float, button: str = "left", num_clicks: int = 1) -> dict:
        """Click at coordinates."""
        return self._exec(
            {
                "action_type": "CLICK",
                "parameters": {"x": x, "y": y, "button": button, "num_clicks": int(num_clicks)},
            }
        )

    def type_text(self, text: str) -> dict:
        """Type text."""
        return self._exec({"action_type": "TYPING", "parameters": {"text": text}})

    def key(self, key: str) -> dict:
        """Press a key."""
        return self._exec({"action_type": "PRESS", "parameters": {"key": key}})

    def scroll(self, dx: int = 0, dy: int = -800) -> dict:
        """Scroll wheel."""
        return self._exec({"action_type": "SCROLL", "parameters": {"dx": int(dx), "dy": int(dy)}})

    def wait(self, seconds: float = 1.0) -> dict:
        """Wait for UI updates."""
        return self._exec({"action_type": "WAIT", "parameters": {"time": float(seconds)}})

    def terminate(self, status: str = "success") -> dict:
        """Terminate task with status."""
        return self._exec({"action_type": "DONE", "parameters": {"status": status}})


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

