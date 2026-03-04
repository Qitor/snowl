"""Interactive control state for console eval loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
import threading


@dataclass
class InteractionController:
    paused: bool = False
    only_failed_focus: bool = False
    group_by: str = "none"  # one of: none/task/agent
    compare_sort: str = "metric"  # one of: metric/status
    compact_mode: bool = False
    rerun_failed_requested: bool = False
    task_filter: list[str] | None = None
    agent_filter: list[str] | None = None
    variant_filter: list[str] | None = None
    status_filter: list[str] | None = None
    focus_task_id: str | None = None
    lock_focus: bool = False
    selected_task_id: str | None = None
    selected_task_index: int = 0
    focused_panel_index: int = 0
    palette_open: bool = False
    show_help: bool = False
    explain_metric: str | None = None
    theme_mode: str = "research"  # one of: contrast/quiet/research/research_redops
    banner_collapsed: bool = False
    panel_mode: str = "auto"  # one of: auto/default/qa_dense/ops_dense/compare_dense
    qa_result_expanded: bool = False
    last_feedback: str = ""
    action_log: list[dict] = field(default_factory=list)
    queued_inputs: list[str] = None  # type: ignore[assignment]
    queued_keys: list[str] = None  # legacy compatibility
    command_mode: bool = False
    command_buffer: str = ""
    command_history: list[str] = field(default_factory=list)
    command_history_limit: int = 128
    command_suggestions: list[str] = field(default_factory=list)
    _command_history_cursor: int = -1
    _command_history_stash: str = ""
    _queue_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.queued_inputs is None:
            self.queued_inputs = []
        if self.queued_keys is None:
            self.queued_keys = []

    def enqueue_input(self, token: str) -> None:
        value = (token or "").strip()
        if not value:
            return
        with self._queue_lock:
            self.queued_inputs.append(value)

    def command_start(self, prefix: str = "/") -> None:
        with self._queue_lock:
            self.command_mode = True
            self.palette_open = True
            self.command_buffer = prefix
            self.command_suggestions = self._compute_suggestions(prefix)
            self._command_history_cursor = -1
            self._command_history_stash = prefix

    def command_append(self, text: str) -> None:
        if not text:
            return
        with self._queue_lock:
            if not self.command_mode:
                self.command_mode = True
                self.palette_open = True
                self.command_buffer = "/"
            self.command_buffer += text
            self.command_suggestions = self._compute_suggestions(self.command_buffer)

    def command_backspace(self) -> None:
        with self._queue_lock:
            if not self.command_mode:
                return
            if self.command_buffer:
                self.command_buffer = self.command_buffer[:-1]
            if not self.command_buffer:
                self.command_mode = False
                self.palette_open = False
                self.command_suggestions = []
                self._command_history_cursor = -1
            else:
                self.command_suggestions = self._compute_suggestions(self.command_buffer)

    def command_cancel(self) -> None:
        with self._queue_lock:
            self.command_mode = False
            self.palette_open = False
            self.command_buffer = ""
            self.command_suggestions = []
            self._command_history_cursor = -1
            self._command_history_stash = ""

    def command_submit(self) -> str | None:
        with self._queue_lock:
            token = self.command_buffer.strip()
            self.command_mode = False
            self.palette_open = False
            self.command_buffer = ""
            self.command_suggestions = []
            self._command_history_cursor = -1
            self._command_history_stash = ""
            self._remember_history(token)
        return token or None

    def command_history_prev(self) -> str:
        with self._queue_lock:
            if not self.command_mode:
                return ""
            if not self.command_history:
                return self.command_buffer
            if self._command_history_cursor < 0:
                self._command_history_stash = self.command_buffer
                self._command_history_cursor = len(self.command_history) - 1
            else:
                self._command_history_cursor = max(0, self._command_history_cursor - 1)
            self.command_buffer = self.command_history[self._command_history_cursor]
            self.command_suggestions = self._compute_suggestions(self.command_buffer)
            return self.command_buffer

    def command_history_next(self) -> str:
        with self._queue_lock:
            if not self.command_mode:
                return ""
            if not self.command_history:
                return self.command_buffer
            if self._command_history_cursor < 0:
                return self.command_buffer
            self._command_history_cursor += 1
            if self._command_history_cursor >= len(self.command_history):
                self._command_history_cursor = -1
                self.command_buffer = self._command_history_stash
            else:
                self.command_buffer = self.command_history[self._command_history_cursor]
            self.command_suggestions = self._compute_suggestions(self.command_buffer)
            return self.command_buffer

    def command_complete(self) -> str:
        with self._queue_lock:
            if not self.command_mode:
                return ""
            body = self.command_buffer[1:] if self.command_buffer.startswith("/") else self.command_buffer
            trimmed = body.lstrip()
            if " " in trimmed:
                return self.command_buffer
            command = trimmed
            if not command:
                self.command_suggestions = [f"/{name}" for name in self._known_commands()[:6]]
                return self.command_buffer
            candidates = [name for name in self._known_commands() if name.startswith(command)]
            if not candidates:
                self.command_suggestions = []
                return self.command_buffer
            common = candidates[0]
            for name in candidates[1:]:
                while common and not name.startswith(common):
                    common = common[:-1]
            if common and common != command:
                self.command_buffer = "/" + common
            elif len(candidates) == 1:
                self.command_buffer = "/" + candidates[0] + " "
            self.command_suggestions = [f"/{name}" for name in candidates[:5]]
            return self.command_buffer

    def handle_key(self, key: str) -> str:
        return self.handle_input(key)

    def _record_action(self, *, input_text: str, action: str, cli_flags: list[str] | None = None, ui_only: bool = False) -> None:
        self.action_log.append(
            {
                "input": input_text,
                "action": action,
                "cli_flags": list(cli_flags or []),
                "ui_only": bool(ui_only),
            }
        )
        self.last_feedback = action

    def sync_task_options(self, task_ids: list[str]) -> None:
        ids = [x for x in task_ids if x]
        if not ids:
            self.selected_task_id = None
            self.selected_task_index = 0
            return
        self.selected_task_index = max(0, min(self.selected_task_index, len(ids) - 1))
        self.selected_task_id = ids[self.selected_task_index]
        if self.lock_focus and self.selected_task_id:
            self.focus_task_id = self.selected_task_id

    def handle_input(self, raw: str) -> str:
        token = raw.strip()
        if not token:
            return ""
        key = token.lower()
        if key.startswith("/"):
            self._remember_history(token)
            action = self._handle_command_palette(token)
            if action:
                self._record_action(input_text=token, action=action, cli_flags=self.to_cli_flags())
            return action

        if key == "p":
            self.paused = not self.paused
            action = "paused" if self.paused else "resumed"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "f":
            self.only_failed_focus = not self.only_failed_focus
            action = f"only_failed_focus={self.only_failed_focus}"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        if key == "a":
            self.group_by = "agent" if self.group_by != "agent" else "none"
            action = f"group_by={self.group_by}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "t":
            self.group_by = "task" if self.group_by != "task" else "none"
            action = f"group_by={self.group_by}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "r":
            self.rerun_failed_requested = True
            action = "rerun_failed_requested=true"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        if key == "m":
            self.compare_sort = "metric"
            action = "compare_sort=metric"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "s":
            self.compare_sort = "status"
            action = "compare_sort=status"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "v":
            self.compact_mode = not self.compact_mode
            action = f"compact_mode={self.compact_mode}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "b":
            self.banner_collapsed = not self.banner_collapsed
            action = f"banner_collapsed={self.banner_collapsed}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "x":
            order = ["contrast", "quiet", "research", "research_redops"]
            try:
                idx = order.index(self.theme_mode)
            except ValueError:
                idx = 0
            self.theme_mode = order[(idx + 1) % len(order)]
            action = f"theme_mode={self.theme_mode}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "u":
            order = ["auto", "default", "qa_dense", "ops_dense", "compare_dense"]
            try:
                idx = order.index(self.panel_mode)
            except ValueError:
                idx = 0
            self.panel_mode = order[(idx + 1) % len(order)]
            action = f"panel_mode={self.panel_mode}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "e":
            self.qa_result_expanded = not self.qa_result_expanded
            action = f"qa_result_expanded={self.qa_result_expanded}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"tab", "\\t"}:
            self.focused_panel_index += 1
            action = f"focused_panel_index={self.focused_panel_index}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "shift+tab":
            self.focused_panel_index = max(0, self.focused_panel_index - 1)
            action = f"focused_panel_index={self.focused_panel_index}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"j", "down"}:
            self.selected_task_index += 1
            action = f"selected_task_index={self.selected_task_index}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"k", "up"}:
            self.selected_task_index = max(0, self.selected_task_index - 1)
            action = f"selected_task_index={self.selected_task_index}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "enter":
            if self.selected_task_id:
                self.focus_task_id = self.selected_task_id
            self.lock_focus = True
            action = f"focus_locked={self.focus_task_id or '*'}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"/", ":"}:
            self.palette_open = True
            action = "palette_open=true"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"?", "help"}:
            self.show_help = not self.show_help
            action = f"show_help={self.show_help}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key.startswith("task="):
            self.task_filter = [x.strip() for x in token[5:].split(",") if x.strip()] or None
            action = f"task_filter={','.join(self.task_filter or []) or '*'}"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        if key.startswith("agent="):
            self.agent_filter = [x.strip() for x in token[6:].split(",") if x.strip()] or None
            action = f"agent_filter={','.join(self.agent_filter or []) or '*'}"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        if key.startswith("variant="):
            self.variant_filter = [x.strip() for x in token[8:].split(",") if x.strip()] or None
            action = f"variant_filter={','.join(self.variant_filter or []) or '*'}"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        if key.startswith("status="):
            self.status_filter = [x.strip() for x in token[7:].split(",") if x.strip()] or None
            action = f"status_filter={','.join(self.status_filter or []) or '*'}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key.startswith("focus="):
            self.focus_task_id = token[6:].strip() or None
            self.lock_focus = self.focus_task_id is not None
            action = f"focus_task_id={self.focus_task_id or '*'}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key == "lock":
            self.lock_focus = not self.lock_focus
            action = f"lock_focus={self.lock_focus}"
            self._record_action(input_text=token, action=action, ui_only=True)
            return action

        if key in {"clear", "reset-filters"}:
            self.task_filter = None
            self.agent_filter = None
            self.variant_filter = None
            self.status_filter = None
            self.focus_task_id = None
            self.lock_focus = False
            action = "filters_cleared=true"
            self._record_action(input_text=token, action=action, ui_only=False, cli_flags=self.to_cli_flags())
            return action

        return ""

    def _handle_command_palette(self, token: str) -> str:
        raw = token.strip()
        body = raw[1:].strip()
        if not body:
            self.palette_open = True
            return "palette_open=true"
        parts = body.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "task":
            self.task_filter = [x.strip() for x in " ".join(args).split(",") if x.strip()] or None
            return f"task_filter={','.join(self.task_filter or []) or '*'}"
        if cmd == "agent":
            self.agent_filter = [x.strip() for x in " ".join(args).split(",") if x.strip()] or None
            return f"agent_filter={','.join(self.agent_filter or []) or '*'}"
        if cmd == "variant":
            self.variant_filter = [x.strip() for x in " ".join(args).split(",") if x.strip()] or None
            return f"variant_filter={','.join(self.variant_filter or []) or '*'}"
        if cmd == "status":
            self.status_filter = [x.strip() for x in " ".join(args).split(",") if x.strip()] or None
            return f"status_filter={','.join(self.status_filter or []) or '*'}"
        if cmd == "focus":
            self.focus_task_id = (" ".join(args).strip() or None)
            self.lock_focus = self.focus_task_id is not None
            return f"focus_task_id={self.focus_task_id or '*'}"
        if cmd == "rerun":
            if args and args[0].lower() == "failed":
                self.rerun_failed_requested = True
                return "rerun_failed_requested=true"
            return "rerun usage: /rerun failed"
        if cmd == "explain":
            metric = " ".join(args).strip()
            self.explain_metric = metric or None
            return f"explain_metric={self.explain_metric or '*'}"
        if cmd == "mode":
            arg = (args[0].lower() if args else "toggle")
            modes = {"auto", "default", "qa_dense", "ops_dense", "compare_dense"}
            if arg == "toggle":
                order = ["auto", "default", "qa_dense", "ops_dense", "compare_dense"]
                try:
                    idx = order.index(self.panel_mode)
                except ValueError:
                    idx = 0
                self.panel_mode = order[(idx + 1) % len(order)]
            elif arg in modes:
                self.panel_mode = arg
            else:
                return "mode usage: /mode [auto|default|qa_dense|ops_dense|compare_dense|toggle]"
            return f"panel_mode={self.panel_mode}"
        if cmd == "qa":
            arg = (args[0].lower() if args else "toggle")
            if arg in {"toggle"}:
                self.qa_result_expanded = not self.qa_result_expanded
            elif arg in {"expand", "open", "full"}:
                self.qa_result_expanded = True
            elif arg in {"collapse", "close", "summary"}:
                self.qa_result_expanded = False
            else:
                return "qa usage: /qa [expand|collapse|toggle]"
            return f"qa_result_expanded={self.qa_result_expanded}"
        if cmd == "theme":
            arg = (args[0].lower() if args else "toggle")
            if arg == "toggle":
                order = ["contrast", "quiet", "research", "research_redops"]
                try:
                    idx = order.index(self.theme_mode)
                except ValueError:
                    idx = 0
                self.theme_mode = order[(idx + 1) % len(order)]
            elif arg in {"contrast", "quiet", "research", "research_redops"}:
                self.theme_mode = arg
            else:
                return "theme usage: /theme [contrast|quiet|research|research_redops|toggle]"
            return f"theme_mode={self.theme_mode}"
        if cmd == "banner":
            arg = (args[0].lower() if args else "toggle")
            if arg == "toggle":
                self.banner_collapsed = not self.banner_collapsed
            elif arg in {"hide", "off", "collapsed"}:
                self.banner_collapsed = True
            elif arg in {"show", "on", "expanded"}:
                self.banner_collapsed = False
            else:
                return "banner usage: /banner [show|hide|toggle]"
            return f"banner_collapsed={self.banner_collapsed}"
        if cmd in {"help", "?"}:
            self.show_help = not self.show_help
            return f"show_help={self.show_help}"
        if cmd in {"clear", "reset"}:
            self.task_filter = None
            self.agent_filter = None
            self.variant_filter = None
            self.status_filter = None
            self.focus_task_id = None
            self.lock_focus = False
            return "filters_cleared=true"
        nearest = self._nearest_command(cmd)
        if nearest:
            return f"unknown_command={cmd} nearest=/{nearest}"
        return f"unknown_command={cmd}"

    def _known_commands(self) -> list[str]:
        return [
            "task",
            "agent",
            "variant",
            "status",
            "focus",
            "rerun",
            "explain",
            "mode",
            "qa",
            "theme",
            "banner",
            "help",
            "clear",
            "reset",
        ]

    def _compute_suggestions(self, buffer: str) -> list[str]:
        text = (buffer or "").strip()
        if not text.startswith("/"):
            return []
        body = text[1:].lstrip()
        if not body:
            return [f"/{name}" for name in self._known_commands()[:6]]
        command = body.split()[0]
        return [f"/{name}" for name in self._known_commands() if name.startswith(command)][:6]

    def _nearest_command(self, command: str) -> str | None:
        nearest = get_close_matches(command or "", self._known_commands(), n=1, cutoff=0.6)
        return nearest[0] if nearest else None

    def _remember_history(self, token: str) -> None:
        value = str(token or "").strip()
        if not value or not value.startswith("/"):
            return
        if self.command_history and self.command_history[-1] == value:
            return
        self.command_history.append(value)
        limit = max(8, int(self.command_history_limit))
        if len(self.command_history) > limit:
            self.command_history = self.command_history[-limit:]

    def consume_inputs(self) -> list[str]:
        with self._queue_lock:
            out = list(self.queued_inputs)
            self.queued_inputs = []
            if self.queued_keys:
                out.extend(self.queued_keys)
                self.queued_keys = []
        return out

    def should_display(
        self,
        *,
        task_id: str | None,
        agent_id: str | None,
        variant_id: str | None,
        status: str | None = None,
    ) -> bool:
        if self.task_filter and (task_id not in self.task_filter):
            return False
        if self.agent_filter and (agent_id not in self.agent_filter):
            return False
        if self.variant_filter and (variant_id not in self.variant_filter):
            return False
        if self.status_filter and (status not in self.status_filter):
            return False
        if self.only_failed_focus and status not in {"error", "incorrect", "limit_exceeded", "cancelled"}:
            return False
        return True

    def to_cli_flags(self) -> list[str]:
        args: list[str] = []
        if self.task_filter:
            args.extend(["--task", ",".join(self.task_filter)])
        if self.agent_filter:
            args.extend(["--agent", ",".join(self.agent_filter)])
        if self.variant_filter:
            args.extend(["--variant", ",".join(self.variant_filter)])
        if self.rerun_failed_requested or self.only_failed_focus:
            args.append("--rerun-failed-only")
        return args
