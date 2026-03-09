"""Translate normalized GUI actions into controller execute payloads."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any


class GuiActionTranslator:
    @staticmethod
    def to_execute_payload(action: dict[str, Any]) -> dict[str, Any] | None:
        if "command" in action:
            command = action.get("command")
            if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
                raise ValueError("command passthrough must be a sequence of args.")
            return {"command": [str(x) for x in command], "shell": bool(action.get("shell", False))}

        action_type = str(action.get("action_type") or "").upper()
        if action_type == "TYPE":
            action_type = "TYPING"
        elif action_type == "KEY":
            key_raw = str(action.get("key", "") or "")
            if "+" in key_raw:
                action_type = "HOTKEY"
            else:
                action_type = "PRESS"
        params = dict(action.get("parameters") or {})
        if not params:
            for key in (
                "x",
                "y",
                "button",
                "click_type",
                "num_clicks",
                "dx",
                "dy",
                "text",
                "key",
                "keys",
                "duration",
                "seconds",
                "time",
            ):
                if key in action:
                    params[key] = action.get(key)
        click_type = str(params.get("click_type", "")).strip().lower()
        if click_type and "button" not in params:
            if click_type in {"left", "right", "middle"}:
                params["button"] = click_type
            params.pop("click_type", None)
        if action_type in {"DONE", "FAIL", "TERMINATE"}:
            return None
        if action_type == "WAIT":
            sec = float(params.get("time", params.get("seconds", 1.0)))
            time.sleep(max(0.0, sec))
            return None
        if action_type in {"MOVE_TO", "MOUSE_MOVE"}:
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            duration = float(params.get("duration", 0.0))
            return GuiActionTranslator._python_payload(f"pyautogui.moveTo({x}, {y}, duration={duration})")
        if action_type == "CLICK":
            kwargs: list[str] = []
            if "button" in params:
                kwargs.append(f"button={repr(str(params.get('button')))}")
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            if "num_clicks" in params:
                kwargs.append(f"clicks={int(params.get('num_clicks', 1))}")
            code = f"pyautogui.click({', '.join(kwargs)})" if kwargs else "pyautogui.click()"
            return GuiActionTranslator._python_payload(code)
        if action_type == "RIGHT_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            code = f"pyautogui.rightClick({', '.join(kwargs)})" if kwargs else "pyautogui.rightClick()"
            return GuiActionTranslator._python_payload(code)
        if action_type == "DOUBLE_CLICK":
            kwargs: list[str] = []
            if "x" in params:
                kwargs.append(f"x={float(params.get('x', 0))}")
            if "y" in params:
                kwargs.append(f"y={float(params.get('y', 0))}")
            code = f"pyautogui.doubleClick({', '.join(kwargs)})" if kwargs else "pyautogui.doubleClick()"
            return GuiActionTranslator._python_payload(code)
        if action_type == "MOUSE_DOWN":
            if "button" in params:
                return GuiActionTranslator._python_payload(
                    f"pyautogui.mouseDown(button={repr(str(params.get('button')))})"
                )
            return GuiActionTranslator._python_payload("pyautogui.mouseDown()")
        if action_type == "MOUSE_UP":
            if "button" in params:
                return GuiActionTranslator._python_payload(
                    f"pyautogui.mouseUp(button={repr(str(params.get('button')))})"
                )
            return GuiActionTranslator._python_payload("pyautogui.mouseUp()")
        if action_type in {"DRAG_TO", "DRAG"}:
            x = float(params.get("x", 0))
            y = float(params.get("y", 0))
            duration = float(params.get("duration", 1.0))
            button = str(params.get("button", "left"))
            return GuiActionTranslator._python_payload(
                f"pyautogui.dragTo({x}, {y}, duration={duration}, button={repr(button)}, mouseDownUp=True)"
            )
        if action_type == "SCROLL":
            commands: list[str] = []
            if "dx" in params:
                commands.append(f"pyautogui.hscroll({int(params.get('dx', 0))})")
            if "dy" in params:
                commands.append(f"pyautogui.vscroll({int(params.get('dy', 0))})")
            if not commands:
                commands.append(f"pyautogui.vscroll({int(params.get('dy', -800))})")
            return GuiActionTranslator._python_payload("; ".join(commands))
        if action_type == "TYPING":
            text = str(params.get("text", ""))
            return GuiActionTranslator._python_payload(f"pyautogui.typewrite({repr(text)})")
        if action_type == "PRESS":
            key = str(params.get("key", "enter"))
            return GuiActionTranslator._python_payload(f"pyautogui.press({repr(key)})")
        if action_type == "KEY_DOWN":
            key = str(params.get("key", ""))
            return GuiActionTranslator._python_payload(f"pyautogui.keyDown({repr(key)})")
        if action_type == "KEY_UP":
            key = str(params.get("key", ""))
            return GuiActionTranslator._python_payload(f"pyautogui.keyUp({repr(key)})")
        if action_type == "HOTKEY":
            keys_raw = params.get("keys")
            if isinstance(keys_raw, str):
                if "+" in keys_raw:
                    keys = [x.strip() for x in keys_raw.split("+") if x.strip()]
                else:
                    keys = [keys_raw]
            elif isinstance(keys_raw, Sequence):
                keys = [str(k) for k in keys_raw if str(k)]
            else:
                keys = []
            if not keys and "key" in params:
                key_raw = str(params.get("key", "") or "")
                if "+" in key_raw:
                    keys = [x.strip() for x in key_raw.split("+") if x.strip()]
            if not keys:
                raise ValueError("HOTKEY action requires non-empty 'keys'.")
            keys_args = ", ".join(repr(k) for k in keys)
            return GuiActionTranslator._python_payload(f"pyautogui.hotkey({keys_args})")
        raise ValueError(f"Unsupported action_type: {action_type}")

    @staticmethod
    def _python_payload(command: str) -> dict[str, Any]:
        return {"command": ["python", "-c", f"import pyautogui; {command}"], "shell": False}
