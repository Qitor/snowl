"""CLI renderer implementations for plan/progress/events/summary output.

Framework role:
- Contains both simple text renderer and live multi-panel renderer used during long-running evals.
- Converts normalized runtime events and monitor state into operator-friendly terminal views.

Runtime/usage wiring:
- Called by CLI/eval orchestration; consumes `normalize_ui_event` and interaction controller state.

Change guardrails:
- Renderer should consume state contracts, not redefine them; keep formatting changes non-breaking for operators.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from snowl.ui.contracts import TaskExecutionStatus, TaskMonitor, normalize_ui_event
from snowl.ui.controls import InteractionController
from snowl.ui.panels import PanelConfig, PanelRegistry, PanelSpec, load_panel_config


@dataclass(frozen=True)
class ThemeTokens:
    title: str
    subtitle: str
    panel_border: str
    panel_title: str
    panel_text: str
    accent: str
    warn: str
    ok: str
    banner_primary: str
    banner_fill: str
    banner_tag: str


@dataclass
class ConsoleRenderer:
    """Lightweight text renderer for MVP CLI interactivity."""

    verbose: bool = True
    width: int | None = None

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def _effective_width(self) -> int:
        if self.width is not None:
            return max(20, int(self.width))
        cols = shutil.get_terminal_size(fallback=(120, 20)).columns
        return max(20, int(cols))

    def _emit(self, text: str) -> None:
        max_width = self._effective_width()
        safe_text = text if len(text) <= max_width else text[: max_width - 1] + ">"
        with self._lock:
            print(safe_text)

    def _debug_value(self, value: Any, *, limit: int = 520) -> str:
        if value is None:
            return "null"
        if isinstance(value, str):
            text = value.replace("\n", "\\n")
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, sort_keys=True)
            except Exception:
                text = str(value)
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _emit_model_debug(self, event: dict[str, Any], *, prefix: str = "[live]") -> None:
        for line in self._model_debug_lines(event, prefix=prefix):
            self._emit(line)

    def _model_debug_lines(self, event: dict[str, Any], *, prefix: str) -> list[str]:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        request = payload.get("request")
        if not isinstance(request, dict):
            request = event.get("request") if isinstance(event.get("request"), dict) else {}
        response = payload.get("response")
        if not isinstance(response, dict):
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
        error_type = payload.get("error_type")
        if error_type is None:
            error_type = event.get("error_type")

        lines: list[str] = []
        if request:
            if "messages" in request:
                lines.append(f"{prefix} provider.request.messages={self._debug_value(request.get('messages'))}")
            if "generation_kwargs" in request:
                lines.append(f"{prefix} provider.request.kwargs={self._debug_value(request.get('generation_kwargs'))}")

        if error_type is not None:
            lines.append(f"{prefix} provider.error_type={self._debug_value(error_type, limit=120)}")

        if response:
            if "message" in response:
                lines.append(f"{prefix} provider.response.message={self._debug_value(response.get('message'))}")
            if "raw" in response:
                lines.append(f"{prefix} provider.response.raw={self._debug_value(response.get('raw'))}")
        return lines

    def render_plan(self, plan: Any) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Plan ===")
        self._emit(
            "mode={mode} tasks={tasks} agents={agents} variants={variants} samples={samples} total_trials={trials}".format(
                mode=plan.mode,
                tasks=len(plan.task_ids),
                agents=len(plan.agent_ids),
                variants=len(getattr(plan, "variant_ids", []) or []),
                samples=plan.sample_count,
                trials=len(plan.trials),
            )
        )

    def render_global(self, *, done: int, total: int, success: int, incorrect: int, other: int) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Global ===")
        self._emit(
            f"progress={done}/{total} success={success} incorrect={incorrect} other={other}"
        )

    def render_trial_start(self, trial: Any, index: int, total: int) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Trial ===")
        self._emit(
            "[{idx}/{total}] task={task} agent={agent} variant={variant} sample={sample}".format(
                idx=index,
                total=total,
                task=trial.task_id,
                agent=trial.agent_id,
                variant=getattr(trial, "variant_id", "default"),
                sample=trial.sample_id,
            )
        )

    def render_trial_finish(self, outcome: Any) -> None:
        if not self.verbose:
            return
        trace_events = outcome.trace.get("trace_events", []) if isinstance(outcome.trace, dict) else []
        latest = trace_events[-1]["event"] if trace_events else "none"
        status = outcome.task_result.status.value
        self._emit(
            "status={status} latest_trace={trace} tokens={tokens}".format(
                status=status,
                trace=latest,
                tokens=(outcome.task_result.usage.total_tokens if outcome.task_result.usage else 0),
            )
        )
        error = getattr(outcome.task_result, "error", None)
        if status == "error" and error is not None:
            code = getattr(error, "code", "unknown")
            msg = str(getattr(error, "message", ""))[:200]
            self._emit(f"error_code={code} error_message={msg}")

    def render_compare(self, aggregate: Any) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Compare ===")
        matrix = getattr(aggregate, "matrix", {}) or {}
        for task_id in sorted(matrix.keys()):
            agent_rows = matrix.get(task_id) or {}
            for agent_id in sorted(agent_rows.keys()):
                metrics = agent_rows[agent_id]
                metric_str = ", ".join(f"{k}={v:.3f}" for k, v in sorted(metrics.items()))
                self._emit(f"task={task_id} agent={agent_id} {metric_str}")

    def render_controls(self) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Controls ===")
        self._emit("keys: p=pause/resume, f=focus-failed, a=group-agent, t=group-task, r=rerun-failed")

    def render_summary(self, summary: Any, artifacts_dir: str, rerun_cmd: str) -> None:
        if not self.verbose:
            return
        self._emit("")
        self._emit("=== Summary ===")
        self._emit(
            "total={total} success={success} incorrect={incorrect} error={error} limit_exceeded={limit} cancelled={cancelled}".format(
                total=summary.total,
                success=summary.success,
                incorrect=summary.incorrect,
                error=summary.error,
                limit=summary.limit_exceeded,
                cancelled=summary.cancelled,
            )
        )
        self._emit(f"artifacts={artifacts_dir}")
        self._emit(f"log={artifacts_dir}/run.log")
        self._emit(f"rerun={rerun_cmd}")

    def render_runtime_event(self, event: dict[str, Any]) -> None:
        if not self.verbose:
            return
        name = str(event.get("event", "runtime.event"))
        if name == "ui.heartbeat":
            return
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        def _pick(key: str) -> Any:
            value = event.get(key)
            if value is None:
                value = payload.get(key)
            if value is None:
                nested = payload.get("payload")
                if isinstance(nested, dict):
                    value = nested.get(key)
            return value

        def _clip(value: Any, *, limit: int = 160) -> str:
            text = str(value).replace("\n", "\\n")
            return text if len(text) <= limit else text[: limit - 1] + "…"

        # Keep runtime stream concise but visible for container startup/debug.
        details = []
        for key in (
            "task_id",
            "agent_id",
            "variant_id",
            "provider_id",
            "model",
            "base_url",
            "project",
            "compose_file",
            "command_text",
            "exit_code",
            "duration_ms",
            "ready",
            "status",
            "score",
            "message",
            "stdout_tail",
            "stderr_tail",
        ):
            value = _pick(key)
            if value is not None:
                details.append(f"{key}={_clip(value)}")
        suffix = (" " + " ".join(details)) if details else ""
        self._emit(f"[live] {name}{suffix}")
        if name in {"runtime.model.query.start", "runtime.model.query.error", "runtime.model.io"}:
            self._emit_model_debug(event)


@dataclass
class LiveConsoleRenderer(ConsoleRenderer):
    """Advanced multi-panel live renderer for long-running eval workflows."""

    max_events: int = 240
    max_failures: int = 120
    max_active_trials: int = 48
    refresh_interval_ms: int = 80
    ui_refresh_profile: str = "balanced"  # smooth/balanced/low_cpu
    theme_mode: str = "research"
    show_banner: bool = True
    ui_mode: str = "auto"  # auto/default/qa_dense/ops_dense/compare_dense

    def __post_init__(self) -> None:
        super().__post_init__()
        self._events: deque[str] = deque(maxlen=max(1, int(self.max_events)))
        self._runtime_events: deque[dict[str, Any]] = deque(maxlen=max(1, int(self.max_events)))
        self._failures: deque[str] = deque(maxlen=max(10, int(self.max_failures)))
        self._active: dict[str, str] = {}
        self._latest_global: dict[str, int] = {"done": 0, "total": 0, "success": 0, "incorrect": 0, "other": 0}
        self._compare_rows: list[str] = []
        self._compare_rows_by_variant: dict[str, list[str]] = {}
        self._compare_ranks: dict[str, int] = {}
        self._compare_focus_metric: str | None = None
        self._compare_leader_rows: list[str] = []
        self._metric_sum: dict[str, float] = {}
        self._metric_count: dict[str, int] = {}
        self._metric_last: dict[str, float] = {}
        self._latest_summary: str | None = None
        self._controller: InteractionController | None = None
        self._last_flush = 0.0
        self._started_wall = time.monotonic()
        self._last_event_wall = self._started_wall
        self._activity_tick = 0
        self._inflight_model_queries = 0
        self._inflight_scorers = 0
        self._inflight_env_commands = 0
        self._env_stream_chunks = 0
        self._activity_label = "idle"
        self._input_status = "unknown"
        self._suppressed = 0
        self._ansi_enabled = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self._task_monitor = TaskMonitor()
        self._trial_context: dict[str, dict[str, Any]] = {}
        self._run_id = "run-local"
        self._benchmark_name = "custom"
        self._plan_mode = "single"
        self._plan_counts = {"tasks": 0, "agents": 0, "variants": 0, "trials": 0}
        self._model_name = ""
        self._model_base_url = ""
        self._panel_config: PanelConfig = load_panel_config(benchmark_name=None)
        self._panel_registry = PanelRegistry()
        self._register_default_panels()
        self._rich_enabled = False
        self._rich_error: str | None = None
        self._rich_console: Any | None = None
        self._rich_live: Any | None = None
        try:
            import rich  # noqa: F401

            # Use rich live rendering only on real TTY to avoid truncated snapshots
            # in non-interactive outputs (tests/log captures).
            self._rich_enabled = bool(self._ansi_enabled)
        except Exception as exc:  # pragma: no cover - fallback path
            self._rich_enabled = False
            self._rich_error = str(exc)

    def bind_controller(self, controller: InteractionController) -> None:
        self._controller = controller

    def configure_panels(self, *, benchmark_name: str | None, project_dir: str | Path | None = None) -> None:
        project_path = Path(project_dir).resolve() if project_dir is not None else None
        self._panel_config = load_panel_config(
            benchmark_name=(benchmark_name or None),
            project_dir=project_path,
        )
        if not self._panel_config.layout.left and not self._panel_config.layout.right:
            self._panel_config = load_panel_config(benchmark_name=None, project_dir=project_path)

    def _resolved_layout(self) -> tuple[list[str], list[str]]:
        mode = self._active_ui_mode()
        has_user_override = any(
            str(src).endswith("panels.yml") or str(src).endswith("panels.yaml")
            for src in (self._panel_config.source_chain or [])
        )
        if mode == "auto" and self._benchmark_name in {"terminalbench", "osworld"} and not has_user_override:
            return (
                ["stage_widget", "env_timeline", "event_stream", "task_queue"],
                ["metric_spotlight", "task_detail", "model_io", "scorer_explain", "compare_board", "failures"],
            )
        if mode == "qa_dense" or (
            mode == "auto" and self._benchmark_name == "strongreject" and not has_user_override
        ):
            return (
                ["stage_widget", "task_queue", "event_stream", "task_detail"],
                ["metric_spotlight", "qa_result", "model_io", "scorer_explain", "failures", "compare_board"],
            )
        if mode == "ops_dense":
            return (
                ["stage_widget", "task_queue", "event_stream", "action_stream", "observation_stream", "env_timeline"],
                ["metric_spotlight", "model_io", "scorer_explain", "compare_board", "failures"],
            )
        if mode == "compare_dense":
            return (
                ["stage_widget", "task_queue", "event_stream", "env_timeline"],
                ["metric_spotlight", "compare_board", "task_detail", "model_io", "scorer_explain", "failures"],
            )
        left = list(self._panel_config.layout.left)
        right = list(self._panel_config.layout.right)
        if not left and not right:
            left = ["task_queue", "task_detail", "event_stream"]
            right = ["stage_widget", "model_io", "scorer_explain", "failures"]
        return left, right

    def _get_spec(self, panel_type: str) -> PanelSpec:
        return self._panel_config.specs.get(panel_type) or PanelSpec(
            panel_type=panel_type,
            title=panel_type.replace("_", " ").upper(),
            source=panel_type,
        )

    def _register_default_panels(self) -> None:
        self._panel_registry.register("task_queue", self._render_panel_task_queue)
        self._panel_registry.register("task_detail", self._render_panel_task_detail)
        self._panel_registry.register("stage_widget", self._render_panel_stage_widget)
        self._panel_registry.register("metric_spotlight", self._render_panel_metric_spotlight)
        self._panel_registry.register("qa_prompt", self._render_panel_qa_prompt)
        self._panel_registry.register("qa_result", self._render_panel_qa_result)
        self._panel_registry.register("event_stream", self._render_panel_event_stream)
        self._panel_registry.register("env_timeline", self._render_panel_env_timeline)
        self._panel_registry.register("action_stream", self._render_panel_action_stream)
        self._panel_registry.register("observation_stream", self._render_panel_observation_stream)
        self._panel_registry.register("model_io", self._render_panel_model_io)
        self._panel_registry.register("scorer_explain", self._render_panel_scorer_explain)
        self._panel_registry.register("compare_board", self._render_panel_compare_board)
        self._panel_registry.register("failures", self._render_panel_failures)

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S")

    def _activity_spinner(self) -> str:
        frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        return frames[self._activity_tick % len(frames)]

    def _activity_text(self) -> str:
        age = max(0.0, time.monotonic() - self._last_event_wall)
        if self._inflight_model_queries > 0:
            phase = f"🔄 querying-model x{self._inflight_model_queries}"
        elif self._inflight_env_commands > 0:
            phase = f"🐳 docker-stream x{self._inflight_env_commands} chunks={self._env_stream_chunks}"
        elif self._inflight_scorers > 0:
            phase = f"🧪 scoring x{self._inflight_scorers}"
        else:
            phase = self._activity_label
        return f"{self._activity_spinner()} activity={phase} last_event={age:0.1f}s"

    def _metrics_overview_text(self, limit: int = 4) -> str:
        if not self._metric_count:
            return "metrics: pending"
        names = sorted(self._metric_count.keys())
        chunks: list[str] = []
        for name in names[: max(1, int(limit))]:
            c = max(1, int(self._metric_count.get(name, 0)))
            avg = float(self._metric_sum.get(name, 0.0)) / float(c)
            last = float(self._metric_last.get(name, 0.0))
            chunks.append(f"{name}=avg:{avg:.3f} n:{c} last:{last:.3f}")
        if len(names) > limit:
            chunks.append(f"+{len(names) - limit} more")
        return "metrics: " + " | ".join(chunks)

    def _ranked_metrics(self) -> list[tuple[str, float, int, float]]:
        rows: list[tuple[str, float, int, float]] = []
        for name, count in self._metric_count.items():
            c = max(1, int(count))
            avg = float(self._metric_sum.get(name, 0.0)) / float(c)
            last = float(self._metric_last.get(name, 0.0))
            rows.append((name, avg, c, last))
        rows.sort(key=lambda x: (-x[2], x[0]))
        return rows

    def _primary_metric(self) -> tuple[str, float, int, float] | None:
        ranked = self._ranked_metrics()
        if not ranked:
            return None
        for preferred in ("accuracy", "strongreject", "score"):
            for row in ranked:
                if row[0] == preferred:
                    return row
        return ranked[0]

    def _secondary_metrics(self, limit: int = 3) -> list[tuple[str, float, int, float]]:
        ranked = self._ranked_metrics()
        primary = self._primary_metric()
        if primary is None:
            return []
        out = [row for row in ranked if row[0] != primary[0]]
        return out[: max(0, int(limit))]

    def _configured_primary_metric_name(self) -> str | None:
        left_layout, right_layout = self._resolved_layout()
        for panel_type in list(left_layout) + list(right_layout):
            if panel_type != "metric_spotlight":
                continue
            spec = self._get_spec(panel_type)
            options = dict(getattr(spec, "options", {}) or {})
            name = str(options.get("primary_metric", "") or "").strip()
            if name:
                return name
        primary = self._primary_metric()
        return primary[0] if primary is not None else None

    def _status_icon(self, status: str) -> str:
        mapping = {
            "queued": "🕒",
            "running": "🏃",
            "scoring": "🧪",
            "success": "✅",
            "incorrect": "⚠️",
            "error": "❌",
            "cancelled": "⏹️",
            "limit_exceeded": "⛔",
        }
        return mapping.get(status, "•")

    def _active_ui_mode(self) -> str:
        if self._controller is not None:
            mode = str(getattr(self._controller, "panel_mode", self.ui_mode) or self.ui_mode).lower()
        else:
            mode = str(self.ui_mode).lower()
        return mode if mode in {"auto", "default", "qa_dense", "ops_dense", "compare_dense"} else "auto"

    def _active_refresh_profile(self) -> str:
        profile = str(self.ui_refresh_profile or "balanced").lower()
        return profile if profile in {"smooth", "balanced", "low_cpu"} else "balanced"

    def heartbeat_interval_s(self) -> float:
        profile = self._active_refresh_profile()
        if profile == "smooth":
            return 0.20
        if profile == "low_cpu":
            return 0.80
        return 0.40

    def _active_theme_mode(self) -> str:
        if self._controller is not None:
            mode = str(getattr(self._controller, "theme_mode", self.theme_mode) or self.theme_mode).lower()
            if mode in {"contrast", "quiet", "research", "research_redops"}:
                return mode
        mode = str(self.theme_mode).lower()
        if mode in {"quiet", "research", "research_redops"}:
            return mode
        return "contrast"

    def _active_banner_visible(self) -> bool:
        if self._controller is not None:
            return not bool(getattr(self._controller, "banner_collapsed", False))
        return bool(self.show_banner)

    def _theme_tokens(self) -> ThemeTokens:
        docker_like_benchmark = self._benchmark_name in {"terminalbench", "osworld"}
        if self._active_theme_mode() == "research_redops":
            return ThemeTokens(
                title="#FFEDEA",
                subtitle="#FFCFC7",
                panel_border="#B85C4C",
                panel_title="#FFAA99",
                panel_text="#FFE4DF",
                accent="#FF8A75",
                warn="#FF6E5B",
                ok="#9FE3B0",
                banner_primary="#FFD2CA",
                banner_fill="#E6785E",
                banner_tag="#FFB199",
            )
        if self._active_theme_mode() == "quiet":
            return ThemeTokens(
                title="#EAF4FF",
                subtitle="#C8D9E8",
                panel_border="#5A6B78",
                panel_title="#CFE3F4",
                panel_text="#DFEBF5",
                accent="#89AFCB",
                warn="#E1A87A",
                ok="#8FC7A3",
                banner_primary="#DCEBFA",
                banner_fill="#8BAFD1",
                banner_tag="#B8C8D7",
            )
        if self._active_theme_mode() == "research":
            if docker_like_benchmark:
                # Ops/container heavy runs get a warmer palette so they are
                # visually distinct from QA-style evals in the terminal.
                return ThemeTokens(
                    title="#FFEDEA",
                    subtitle="#FFCFC7",
                    panel_border="#B85C4C",
                    panel_title="#FFAA99",
                    panel_text="#FFE4DF",
                    accent="#FF8A75",
                    warn="#FF6E5B",
                    ok="#9FE3B0",
                    banner_primary="#FFD2CA",
                    banner_fill="#E6785E",
                    banner_tag="#FFB199",
                )
            return ThemeTokens(
                title="#E8EEFF",
                subtitle="#AEB8CC",
                panel_border="#607AA3",
                panel_title="#B4C7FF",
                panel_text="#E2E8FA",
                accent="#95A7FF",
                warn="#FF8E7A",
                ok="#8DE3A7",
                banner_primary="#C4CEFF",
                banner_fill="#7BB2E6",
                banner_tag="#B574D8",
            )
        return ThemeTokens(
            title="#E8F7FF",
            subtitle="#B9E7FF",
            panel_border="#4C8DB8",
            panel_title="#8ED1FC",
            panel_text="#D7F1FF",
            accent="#5FA8D3",
            warn="#FF9E7A",
            ok="#9EF7C2",
            banner_primary="#B7D9F8",
            banner_fill="#77B6E6",
            banner_tag="#AC75D1",
        )

    def _rich_row_style(self, row: str, tokens: ThemeTokens) -> str:
        low = row.lower()
        if "status=success" in low or " ✅ " in low or low.startswith("✅"):
            return tokens.ok
        if "status=error" in low or "status=incorrect" in low or " ❌ " in low or low.startswith("❌"):
            return tokens.warn
        if "querying-model" in low or "scoring" in low or low.startswith("🔄"):
            return tokens.accent
        if "status=queued" in low or "🕒" in low:
            return tokens.subtitle
        if "status=running" in low or "🏃" in low:
            return tokens.panel_title
        return tokens.panel_text

    def _render_banner_lines(self, width: int) -> list[str]:
        if not self._active_banner_visible():
            return [f"Snowl Live  run={self._run_id}  benchmark={self._benchmark_name}"]
        if width >= 96:
            return [
                " /\\_ _/\\    /\\_ _/\\    /\\_ _/\\    /\\_ _/\\    /\\_ _/\\ ",
                "( o v o )  ( o v o )  ( o v o )  ( o v o )  ( o v o )",
                f"minimalist stream runtime • theme={self._active_theme_mode()}",
            ]
        return [f"/\\_ _/\\ ( o v o )  minimalist runtime • theme={self._active_theme_mode()}"]

    def _render_banner_rich_rows(self, width: int, tokens: ThemeTokens) -> list[Any]:
        from rich.text import Text

        rows: list[Any] = []
        if width >= 96:
            top = Text()
            top.append(" /\\_ _/\\    /\\_ _/\\    /\\_ _/\\    /\\_ _/\\    /\\_ _/\\ ", style=f"bold {tokens.banner_fill}")
            rows.append(top)
            mid = Text()
            mid.append("( o v o )  ( o v o )  ( o v o )  ( o v o )  ( o v o )", style=f"bold {tokens.banner_primary}")
            rows.append(mid)
            tag = Text()
            tag.append("minimalist stream runtime", style=tokens.subtitle)
            tag.append(" • ", style=tokens.subtitle)
            tag.append("theme=", style=tokens.subtitle)
            tag.append(self._active_theme_mode(), style=f"bold {tokens.banner_tag}")
            rows.append(tag)
        else:
            compact = Text()
            compact.append("/\\_ _/\\ ( o v o )", style=f"bold {tokens.banner_fill}")
            compact.append("  minimalist runtime • theme=", style=tokens.subtitle)
            compact.append(self._active_theme_mode(), style=f"bold {tokens.banner_tag}")
            rows.append(compact)
        return rows

    def _phase_tag(self, event_name: str) -> str:
        name = event_name.lower()
        if "container" in name or "compose" in name:
            return "container"
        if "tool" in name or ".action" in name:
            return "tool"
        if "scorer" in name or "judge" in name:
            return "scorer"
        if "sandbox" in name:
            return "sandbox"
        if "trial" in name:
            return "trial"
        if "control" in name:
            return "control"
        return "runtime"

    def _monitor_key(self, *, task_id: str, agent_id: str, variant_id: str, sample_id: str | None) -> str:
        return f"{task_id}::{agent_id}::{variant_id}::{sample_id or '-'}"

    def _pick_selected_task_key(self) -> str | None:
        states = self._task_monitor.list_states()
        if not states:
            return None
        if self._controller is not None:
            ids = sorted({s.task_id for s in states})
            sync = getattr(self._controller, "sync_task_options", None)
            if callable(sync):
                sync(ids)
            selected_task_id = getattr(self._controller, "selected_task_id", None)
            if selected_task_id:
                for s in states:
                    if s.task_id == selected_task_id:
                        return s.key
        if self._controller and self._controller.focus_task_id:
            for s in states:
                if s.task_id == self._controller.focus_task_id:
                    return s.key
        for s in states:
            if s.status in {TaskExecutionStatus.RUNNING, TaskExecutionStatus.SCORING}:
                return s.key
        return states[0].key

    def _resolve_qa_context_key(self) -> str | None:
        selected_key = self._pick_selected_task_key()
        if selected_key is not None:
            ctx = self._trial_context.get(selected_key, {})
            if any(ctx.get(k) is not None for k in ("output_content", "judge_json", "final_score")) or ctx.get("score_lines"):
                return selected_key
        # Fallback to the most recently updated context that actually has QA data.
        for key in reversed(list(self._trial_context.keys())):
            ctx = self._trial_context.get(key, {})
            if any(ctx.get(k) is not None for k in ("output_content", "judge_json", "final_score")) or ctx.get("score_lines"):
                return key
        return selected_key

    def _panel_visible(self, spec: PanelSpec) -> bool:
        rule = (spec.visibility or "always").strip().lower()
        if rule in {"always", "true", "1"}:
            return True
        if rule == "when_env_present":
            return any("[container]" in x or "[sandbox]" in x or "compose" in x for x in self._events)
        if rule == "when_model_io_present":
            return self._has_model_io()
        if rule == "when_scorer_present":
            return any("runtime.scorer.finish" in x for x in self._events) or self._has_scorer_explain()
        return True

    def _has_model_io(self) -> bool:
        return any("model_io" in line or "content=" in line for line in self._events)

    def _has_scorer_explain(self) -> bool:
        return any("explanations=" in line or "runtime.scorer.finish" in line for line in self._events)

    def _render_panel_task_queue(self, spec: PanelSpec, mode: str) -> list[str]:
        rows = [
            s
            for s in self._task_monitor.list_states()
            if (self._controller is None or self._controller.should_display(
                task_id=s.task_id,
                agent_id=s.agent_id,
                variant_id=s.variant_id,
                status=s.status.value,
            ))
        ]
        if not rows:
            return ["none"]

        def _clip(text: str, limit: int = 96) -> str:
            return text if len(text) <= limit else text[: limit - 1] + "…"

        out: list[str] = []
        max_rows = 6 if mode == "rich" else 8
        for s in rows[:max_rows]:
            out.append(
                _clip(
                    f"{self._status_icon(s.status.value)} task={s.task_id} status={s.status.value} step={s.step_count} dur={s.duration_ms} agent={s.agent_id}#{s.variant_id}"
                )
            )
        return out

    def _render_panel_task_detail(self, spec: PanelSpec, mode: str) -> list[str]:
        selected_key = self._pick_selected_task_key()
        if selected_key is None:
            return ["none"]
        selected = next((s for s in self._task_monitor.list_states() if s.key == selected_key), None)
        if selected is None:
            return ["none"]
        ctx = self._trial_context.get(selected.key, {})
        out = [
            f"task={selected.task_id} agent={selected.agent_id} variant={selected.variant_id} sample={selected.sample_id}",
            f"status={selected.status.value} step={selected.step_count} duration_ms={selected.duration_ms}",
        ]
        if ctx.get("input") is not None:
            out.append(f"input={ctx.get('input')}")
        if ctx.get("instruction") is not None:
            out.append(f"instruction={ctx.get('instruction')}")
        if selected.latest_action:
            out.append(f"latest_action={selected.latest_action}")
        if selected.latest_observation:
            out.append(f"latest_observation={selected.latest_observation}")
        if selected.latest_message:
            out.append(f"latest_message={selected.latest_message}")
        return out

    def _render_panel_stage_widget(self, spec: PanelSpec, mode: str) -> list[str]:
        selected_key = self._pick_selected_task_key()
        selected = None
        if selected_key is not None:
            selected = next((s for s in self._task_monitor.list_states() if s.key == selected_key), None)

        stage_by_status = {
            "queued": "queued",
            "running": "agent",
            "scoring": "scoring",
            "success": "done",
            "incorrect": "done",
            "error": "done",
            "cancelled": "done",
            "limit_exceeded": "done",
        }
        current = stage_by_status.get(getattr(selected, "status", None).value if selected is not None else "queued", "queued")
        if self._inflight_model_queries > 0:
            current = "querying"
        elif self._inflight_scorers > 0:
            current = "scoring"

        order = ["queued", "querying", "agent", "scoring", "done"]
        done_idx = order.index(current) if current in order else 0

        def _mark(idx: int, name: str) -> str:
            if idx < done_idx:
                return f"✅ {name}"
            if idx == done_idx:
                return f"🔄 {name}"
            return f"⬜ {name}"

        capsule = " -> ".join(_mark(i, n) for i, n in enumerate(order))
        out = [capsule, self._activity_text()]
        if selected is not None:
            out.append(
                f"selected task={selected.task_id} status={selected.status.value} step={selected.step_count} duration_ms={selected.duration_ms}"
            )
        out.append(
            f"inflight model={self._inflight_model_queries} scorer={self._inflight_scorers}"
        )
        return out

    def _render_panel_metric_spotlight(self, spec: PanelSpec, mode: str) -> list[str]:
        opts = dict(getattr(spec, "options", {}) or {})
        top_k = int(opts.get("top_k", 3) or 3)
        primary_name = str(opts.get("primary_metric", "") or "").strip()
        ranked = self._ranked_metrics()
        if not ranked:
            if self._compare_leader_rows:
                metric_name = self._compare_focus_metric or (primary_name or "best")
                out = [f"pending metrics cache; leaderboard({metric_name}):"]
                out.extend(self._compare_leader_rows[:3])
                return out
            return ["pending (no scored trials yet)"]

        primary = None
        if primary_name:
            for row in ranked:
                if row[0] == primary_name:
                    primary = row
                    break
        if primary is None:
            primary = self._primary_metric() or ranked[0]

        out: list[str] = []
        pn, pa, pc, pl = primary
        trend = pl - pa
        trend_icon = "↗" if trend > 0.01 else ("↘" if trend < -0.01 else "→")
        out.append(f"🎯 primary={pn} avg={pa:.3f} n={pc} last={pl:.3f} trend={trend_icon}{trend:+.3f}")
        out.append("top metrics:")
        for name, avg, count, last in ranked[: max(1, top_k)]:
            icon = "⭐" if name == pn else "•"
            out.append(f"{icon} {name} avg={avg:.3f} n={count} last={last:.3f}")
        if self._compare_leader_rows:
            metric_name = self._compare_focus_metric or pn
            out.append(f"leaderboard({metric_name}):")
            out.extend(self._compare_leader_rows[:3])
        return out

    def _render_panel_qa_prompt(self, spec: PanelSpec, mode: str) -> list[str]:
        selected_key = self._pick_selected_task_key()
        if selected_key is None:
            return ["none"]
        ctx = self._trial_context.get(selected_key, {})
        out: list[str] = []
        prompt = ctx.get("input")
        instruction = ctx.get("instruction")
        metadata = ctx.get("metadata")
        target = ctx.get("target")
        if instruction is not None:
            out.append("instruction:")
            out.append(str(instruction)[:500])
        if prompt is not None:
            out.append("prompt:")
            out.append(str(prompt)[:700])
        if target is not None:
            out.append(f"target={str(target)[:220]}")
        if metadata is not None:
            out.append(f"meta={str(metadata)[:240]}")
        return out or ["none"]

    def _render_panel_qa_result(self, spec: PanelSpec, mode: str) -> list[str]:
        selected_key = self._resolve_qa_context_key()
        if selected_key is None:
            return ["pending (waiting for first model/scorer result)"]
        ctx = self._trial_context.get(selected_key, {})
        out: list[str] = []
        expanded = bool(getattr(self._controller, "qa_result_expanded", False)) if self._controller is not None else False
        output = ctx.get("output_content")
        if output is not None:
            out.append("output:")
            output_text = str(output)
            if expanded:
                out.append(output_text[:1800])
            else:
                out.append(output_text[:360])
                if len(output_text) > 360:
                    out.append("… (collapsed, use /qa expand or key 'e')")
        judge = ctx.get("judge_json")
        if judge is not None:
            out.append("judge_json:")
            judge_text = str(judge)
            if expanded:
                out.append(judge_text[:1200])
            else:
                out.append(judge_text[:260])
                if len(judge_text) > 260:
                    out.append("… (collapsed)")
        final_score = ctx.get("final_score")
        if final_score is not None:
            verdict = "PASS ✅" if float(final_score) >= 0.5 else "FAIL ❌"
            out.append(f"verdict={verdict} final_score={float(final_score):.3f}")
        score_lines = ctx.get("score_lines")
        if score_lines:
            out.append("metrics:")
            for row in list(score_lines)[: (12 if expanded else 6)]:
                out.append(str(row)[:240])
        if out:
            return out
        return ["pending (selected task has no scored output yet)"]

    def _render_panel_event_stream(self, spec: PanelSpec, mode: str) -> list[str]:
        lines = [x for x in self._events if "ui.heartbeat" not in x]
        if not lines:
            return ["none"]

        def _priority(row: str) -> int:
            if "runtime.env.command." in row or "container." in row or "docker" in row or "compose" in row:
                return 0
            if "runtime.model.query." in row:
                return 1
            if "runtime.trial." in row or "runtime.scorer." in row:
                return 2
            if "error" in row.lower() or "failed" in row.lower():
                return 3
            return 9

        max_rows = 12 if mode == "rich" else 10
        window = lines[-80:]
        ranked = sorted(enumerate(window), key=lambda item: (_priority(item[1]), item[0]))
        selected_idx = sorted(idx for idx, _ in ranked[:max_rows])
        selected = [window[i] for i in selected_idx]
        return selected[-max_rows:] or ["none"]

    def _render_panel_env_timeline(self, spec: PanelSpec, mode: str) -> list[str]:
        relevant: list[dict[str, Any]] = []
        for ev in self._runtime_events:
            name = str(ev.get("event", ""))
            phase = str(ev.get("phase", ""))
            if (
                phase == "env"
                or name.startswith("runtime.env.command.")
                or "container" in name
                or "compose" in name
                or "docker" in name
            ):
                relevant.append(ev)
        if not relevant:
            return ["none"]

        def _short(text: Any, limit: int = 72) -> str:
            s = str(text).replace("\n", " ").strip()
            if len(s) <= limit:
                return s
            return s[: limit - 1] + "…"

        out: list[str] = []
        for ev in relevant[-12:]:
            ts = str(ev.get("time", ""))
            name = str(ev.get("event", ""))
            payload = ev.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            nested_payload = payload.get("payload")
            nested_payload = nested_payload if isinstance(nested_payload, dict) else {}

            def _pv(key: str) -> Any:
                if key in payload and payload.get(key) is not None:
                    return payload.get(key)
                return nested_payload.get(key)

            if name in {"runtime.env.command.stdout", "runtime.env.command.stderr"}:
                chunk = _pv("chunk")
                if chunk:
                    stream_icon = "📤" if name.endswith(".stdout") else "📥"
                    out.append(f"{stream_icon} {ts} {str(chunk)[:120]}")
                continue
            short_name = name.split(".")[-1] if "." in name else name
            project = _pv("project")
            exit_code = _pv("exit_code")
            duration_ms = _pv("duration_ms")
            command_text = _pv("command_text")
            prefix = "✅" if exit_code == 0 else ("❌" if isinstance(exit_code, int) and exit_code != 0 else "🐳")
            parts = [f"{prefix} {ts} {name} ({short_name})"]
            if project:
                parts.append(f"project={_short(project, 48)}")
            if exit_code is not None:
                parts.append(f"exit={exit_code}")
            if duration_ms is not None:
                parts.append(f"dur={duration_ms}ms")
            if command_text:
                parts.append(f"cmd={_short(command_text, 86)}")
            out.append(" ".join(parts))

            stderr_tail = _pv("stderr_tail")
            if stderr_tail and isinstance(stderr_tail, str) and stderr_tail.strip():
                out.append(f"   ↳ stderr: {_short(stderr_tail, 120)}")
            stdout_tail = _pv("stdout_tail")
            if stdout_tail and isinstance(stdout_tail, str) and stdout_tail.strip() and exit_code not in (None, 0):
                out.append(f"   ↳ stdout: {_short(stdout_tail, 120)}")
        return out

    def _render_panel_action_stream(self, spec: PanelSpec, mode: str) -> list[str]:
        lines = [x for x in self._events if "[tool]" in x or ".action" in x or "command" in x]
        return lines[-8:] if lines else ["none"]

    def _render_panel_observation_stream(self, spec: PanelSpec, mode: str) -> list[str]:
        lines = [x for x in self._events if "observe" in x or "observation" in x or "capture" in x]
        return lines[-8:] if lines else ["none"]

    def _render_panel_model_io(self, spec: PanelSpec, mode: str) -> list[str]:
        lines = [x for x in self._events if "model_io" in x or "content=" in x or "runtime.trial.finish" in x]
        selected_key = self._pick_selected_task_key()
        if selected_key:
            ctx = self._trial_context.get(selected_key, {})
            prompt = ctx.get("input")
            instruction = ctx.get("instruction")
            if prompt is not None:
                lines.insert(0, f"prompt={str(prompt)[:300]}")
            if instruction is not None:
                lines.insert(1, f"instruction={str(instruction)[:300]}")
        return lines[-10:] if lines else ["none"]

    def _render_panel_scorer_explain(self, spec: PanelSpec, mode: str) -> list[str]:
        lines = [x for x in self._events if "runtime.scorer.finish" in x or "explanations=" in x]
        return lines[-8:] if lines else ["none"]

    def _render_panel_compare_board(self, spec: PanelSpec, mode: str) -> list[str]:
        if not self._compare_rows:
            return ["pending"]
        focus = self._compare_focus_metric or "best"
        rows = [f"focus_metric={focus}"]
        options = dict(getattr(spec, "options", {}) or {})
        group_by_variant = bool(options.get("group_by_variant", False))
        if self._active_ui_mode() == "compare_dense":
            group_by_variant = True
        max_rows = int(options.get("max_rows", 12 if mode == "rich" else 16))
        if group_by_variant and self._compare_rows_by_variant:
            for variant, entries in sorted(self._compare_rows_by_variant.items()):
                rows.append(f"variant={variant}")
                rows.extend(entries[: max(1, max_rows // max(1, len(self._compare_rows_by_variant)))])
        else:
            rows.extend(self._compare_rows[:max_rows])
        return rows

    def _render_panel_failures(self, spec: PanelSpec, mode: str) -> list[str]:
        return list(self._failures)[-8:] or ["none"]

    def _should_render(self, force: bool = False) -> bool:
        now = time.monotonic()
        if force:
            self._last_flush = now
            return True
        profile_ms = 80
        if self._active_refresh_profile() == "smooth":
            profile_ms = 40
        elif self._active_refresh_profile() == "low_cpu":
            profile_ms = 160
        configured_ms = int(self.refresh_interval_ms)
        target_ms = profile_ms if configured_ms == 80 else configured_ms
        min_gap = max(0.01, float(target_ms) / 1000.0)
        if (now - self._last_flush) < min_gap:
            self._suppressed += 1
            return False
        self._last_flush = now
        return True

    def _flush_dashboard(self, *, force: bool = False) -> None:
        if not self.verbose:
            return
        if not self._should_render(force=force):
            return
        self._activity_tick += 1
        if self._suppressed > 0:
            self._events.append(f"{self._now()} [runtime] ui.throttle suppressed={self._suppressed}")
            self._suppressed = 0
        width = self._effective_width()
        if self._rich_enabled:
            self._flush_dashboard_rich(width=width)
            return
        if self._ansi_enabled:
            # Full-screen style redraw for a stable, intuitive live dashboard.
            with self._lock:
                print("\033[2J\033[H", end="")

        def _hr(ch: str = "-") -> str:
            return ch * max(20, width)

        def _bar(done: int, total: int) -> str:
            t = max(1, total)
            ratio = max(0.0, min(1.0, float(done) / float(t)))
            slots = max(10, min(40, width // 4))
            filled = int(round(slots * ratio))
            return "[" + ("#" * filled) + ("." * (slots - filled)) + f"] {done}/{total}"

        self._emit(_hr("="))
        for line in self._render_banner_lines(width):
            self._emit(line)
        self._emit(_hr("="))
        g = self._latest_global
        success_rate = (100.0 * g["success"] / max(1, g["done"])) if g["done"] else 0.0
        error_count = max(0, g["other"])
        error_rate = (100.0 * error_count / max(1, g["done"])) if g["done"] else 0.0
        self._emit(
            "PROGRESS {bar} | success={success} incorrect={incorrect} other={other}".format(
                bar=_bar(g["done"], g["total"]),
                done=g["done"],
                total=g["total"],
                success=g["success"],
                incorrect=g["incorrect"],
                other=g["other"],
            )
        )
        self._emit(
            "EVAL OVERVIEW benchmark={bench} run={run} mode={mode} tasks={tasks} agents={agents} variants={variants} trials={trials} success_rate={sr:.1f}% error_rate={er:.1f}%".format(
                bench=self._benchmark_name,
                run=self._run_id,
                mode=self._plan_mode,
                tasks=self._plan_counts["tasks"],
                agents=self._plan_counts["agents"],
                variants=self._plan_counts["variants"],
                trials=self._plan_counts["trials"],
                sr=success_rate,
                er=error_rate,
            )
        )
        primary = self._primary_metric()
        if primary is None:
            self._emit("KPI primary=pending")
        else:
            name, avg, count, last = primary
            secondary = " | ".join(
                f"{n}:{a:.3f}"
                for n, a, _c, _l in self._secondary_metrics(limit=2)
            ) or "none"
            self._emit(f"KPI primary={name} avg={avg:.3f} n={count} last={last:.3f} secondary={secondary}")
        self._emit(self._metrics_overview_text(limit=3))
        self._emit("LIVE " + self._activity_text())
        if self._controller is not None:
            flags = []
            if self._controller.paused:
                flags.append("paused")
            if self._controller.only_failed_focus:
                flags.append("focus=failed")
            if self._controller.compact_mode:
                flags.append("mode=compact")
            if self._controller.task_filter:
                flags.append("task=" + ",".join(self._controller.task_filter))
            if self._controller.agent_filter:
                flags.append("agent=" + ",".join(self._controller.agent_filter))
            if self._controller.variant_filter:
                flags.append("variant=" + ",".join(self._controller.variant_filter))
            if self._controller.status_filter:
                flags.append("status=" + ",".join(self._controller.status_filter))
            flags.append(f"sort={self._controller.compare_sort}")
            flags.append(f"theme={self._active_theme_mode()}")
            flags.append(f"banner={'on' if self._active_banner_visible() else 'off'}")
            flags.append(f"mode={self._active_ui_mode()}")
            self._emit("STATE " + " ".join(flags))
        self._emit(_hr())

        left_layout, right_layout = self._resolved_layout()
        if width < 90:
            # Narrow fallback: keep information linear and compact.
            for panel_type in left_layout[:3]:
                spec = self._get_spec(panel_type)
                fn = self._panel_registry.get(panel_type)
                if fn is None or not self._panel_visible(spec):
                    continue
                self._emit(spec.title)
                for line in fn(spec, "text")[:4]:
                    self._emit("- " + line)
            return

        for panel_type in left_layout:
            spec = self._get_spec(panel_type)
            fn = self._panel_registry.get(panel_type)
            if fn is None or not self._panel_visible(spec):
                continue
            self._emit(spec.title)
            for line in fn(spec, "text"):
                self._emit("- " + line)
            self._emit(_hr())

        for panel_type in right_layout:
            spec = self._get_spec(panel_type)
            fn = self._panel_registry.get(panel_type)
            if fn is None or not self._panel_visible(spec):
                continue
            self._emit(spec.title)
            rows = fn(spec, "text")
            if panel_type == "compare_board" and self._controller is not None and self._controller.compact_mode:
                rows = rows[:6]
            for line in rows:
                self._emit("- " + line)
            self._emit(_hr())

        if self._latest_summary:
            self._emit("summary " + self._latest_summary)
        if self._controller is not None:
            cmd_buf = str(getattr(self._controller, "command_buffer", "") or "")
            cmd_mode = bool(getattr(self._controller, "command_mode", False))
            if cmd_mode or cmd_buf:
                cursor = "|" if cmd_mode else ""
                self._emit(f"command> {cmd_buf}{cursor}")

    def _flush_dashboard_rich(self, *, width: int) -> None:
        from rich import box
        from rich.console import Console, Group
        from rich.layout import Layout
        from rich.live import Live
        from rich.panel import Panel
        from rich.progress_bar import ProgressBar
        from rich.table import Table
        from rich.text import Text

        if self._rich_console is None:
            self._rich_console = Console(
                file=sys.stdout,
                force_terminal=self._ansi_enabled,
                width=width,
                highlight=False,
                color_system="truecolor",
            )
        console = self._rich_console

        with self._lock:
            if self._ansi_enabled:
                console.width = width

            tokens = self._theme_tokens()
            g = self._latest_global
            total = max(1, int(g["total"]))
            done = max(0, int(g["done"]))
            pct = (done / total) * 100.0
            success_rate = (100.0 * g["success"] / max(1, done)) if done else 0.0
            error_rate = (100.0 * g["other"] / max(1, done)) if done else 0.0
            throughput = float(done) / max(1e-6, time.monotonic() - self._started_wall)

            progress_table = Table.grid(expand=True)
            progress_table.add_column(ratio=3)
            progress_table.add_column(ratio=2)
            progress_table.add_row(
                ProgressBar(total=total, completed=done, width=max(16, min(48, width // 3))),
                Text(
                    f"{done}/{total} ({pct:5.1f}%)  ok={g['success']}  incorrect={g['incorrect']}  other={g['other']}",
                    style=f"bold {tokens.title}",
                ),
            )
            state_flags: list[str] = []
            if self._controller is not None:
                if self._controller.paused:
                    state_flags.append("paused")
                if self._controller.only_failed_focus:
                    state_flags.append("focus=failed")
                if self._controller.compact_mode:
                    state_flags.append("compact")
                if self._controller.task_filter:
                    state_flags.append("task=" + ",".join(self._controller.task_filter))
                if self._controller.agent_filter:
                    state_flags.append("agent=" + ",".join(self._controller.agent_filter))
                if self._controller.variant_filter:
                    state_flags.append("variant=" + ",".join(self._controller.variant_filter))
                state_flags.append(f"sort={self._controller.compare_sort}")
                state_flags.append(f"mode={self._active_ui_mode()}")
            overview_table = Table.grid(expand=True)
            overview_table.add_column(ratio=1)
            overview_table.add_column(ratio=1)
            overview_table.add_row(
                Text(f"benchmark: {self._benchmark_name}", style=tokens.panel_text),
                Text(f"run: {self._run_id}", style=tokens.panel_text),
            )
            overview_table.add_row(
                Text(
                    "tasks={tasks} agents={agents} variants={variants} trials={trials}".format(
                        tasks=self._plan_counts["tasks"],
                        agents=self._plan_counts["agents"],
                        variants=self._plan_counts["variants"],
                        trials=self._plan_counts["trials"],
                    ),
                    style=tokens.panel_text,
                ),
                Text(
                    f"mode={self._plan_mode} success_rate={success_rate:.1f}% error_rate={error_rate:.1f}%",
                    style=tokens.panel_text,
                ),
            )
            overview_table.add_row(
                Text(f"throughput={throughput:.2f} items/s", style=tokens.panel_text),
                Text(
                    "filters: task={task} agent={agent} variant={variant} status={status}".format(
                        task=",".join(self._controller.task_filter or []) if self._controller else "*",
                        agent=",".join(self._controller.agent_filter or []) if self._controller else "*",
                        variant=",".join(self._controller.variant_filter or []) if self._controller else "*",
                        status=",".join(self._controller.status_filter or []) if self._controller else "*",
                    ),
                    style=tokens.panel_text,
                ),
            )
            overview_table.add_row(
                Text(self._activity_text(), style=tokens.subtitle),
                Text(
                    f"inflight(model={self._inflight_model_queries}, scorer={self._inflight_scorers}) input={self._input_status}",
                    style=tokens.subtitle,
                ),
            )
            overview_table.add_row(
                Text(self._metrics_overview_text(limit=3), style=tokens.subtitle),
                Text("", style=tokens.subtitle),
            )
            model_text = self._model_name or "(unset)"
            base_url_text = self._model_base_url or "(unset)"
            overview_table.add_row(
                Text(f"model: {model_text}", style=tokens.subtitle),
                Text(f"base_url: {base_url_text}", style=tokens.subtitle),
            )

            primary = self._primary_metric()
            if primary is None:
                primary_text = "PRIMARY KPI: pending"
                secondary_text = "secondary: pending"
            else:
                pname, pavg, pcount, plast = primary
                primary_text = f"PRIMARY KPI {pname}  avg={pavg:.3f}  n={pcount}  last={plast:.3f}"
                secondary = self._secondary_metrics(limit=3)
                secondary_text = (
                    "secondary: " + " | ".join(f"{n}:{a:.3f}" for n, a, _c, _l in secondary)
                    if secondary
                    else "secondary: none"
                )
            kpi_panel = Panel(
                Group(
                    Text(primary_text, style=f"bold {tokens.title}"),
                    Text(secondary_text, style=tokens.subtitle),
                ),
                title=f"[bold {tokens.panel_title}]KPI STRIP[/]",
                border_style=tokens.panel_border,
                box=box.ROUNDED,
                padding=(0, 1),
            )

            progress_panel = Panel(
                Group(
                    progress_table,
                    overview_table,
                    Text(
                        "state: "
                        + (" ".join(state_flags) if state_flags else "default")
                        + f" theme={self._active_theme_mode()} banner={'on' if self._active_banner_visible() else 'off'}",
                        style=tokens.subtitle,
                    ),
                ),
                title=f"[bold {tokens.panel_title}]EVAL OVERVIEW[/]",
                border_style=tokens.panel_border,
                box=box.ROUNDED,
                padding=(0, 1),
            )
            banner_lines = self._render_banner_lines(width)
            banner_rows = self._render_banner_rich_rows(width, tokens)
            banner_grid = Table.grid(expand=True)
            banner_grid.add_column(justify="left", ratio=1)
            for row in banner_rows:
                banner_grid.add_row(row)
            banner_grid.add_row(
                Text(
                    "run={run}  benchmark={bench}  panel={panel}".format(
                        run=self._run_id,
                        bench=self._benchmark_name,
                        panel=(
                            getattr(self._controller, "focused_panel_index", 0)
                            if self._controller is not None
                            else 0
                        ),
                    ),
                    style=tokens.subtitle,
                )
            )
            top_bar = Panel(
                banner_grid,
                border_style=tokens.accent,
                box=(box.MINIMAL if self._active_theme_mode() == "quiet" else box.SQUARE),
                padding=(0, 1),
            )

            def _panel_to_rich(spec: PanelSpec) -> Panel:
                lines = self._panel_registry.get(spec.panel_type)(spec, "rich")  # type: ignore[union-attr]
                body = Table.grid(expand=True)
                if not lines:
                    lines = ["none"]
                for row in lines:
                    body.add_row(Text(str(row), style=self._rich_row_style(str(row), tokens)))
                return Panel(
                    body,
                    title=f"[bold {tokens.panel_title}]{spec.title}[/]",
                    border_style=tokens.panel_border,
                    box=(box.MINIMAL if self._active_theme_mode() == "quiet" else box.ROUNDED),
                    padding=(0, 1),
                )

            left_layout, right_layout = self._resolved_layout()
            left_panels = []
            for panel_type in left_layout:
                spec = self._get_spec(panel_type)
                fn = self._panel_registry.get(panel_type)
                if fn is None or not self._panel_visible(spec):
                    continue
                left_panels.append(_panel_to_rich(spec))

            right_panels = []
            for panel_type in right_layout:
                spec = self._get_spec(panel_type)
                fn = self._panel_registry.get(panel_type)
                if fn is None or not self._panel_visible(spec):
                    continue
                right_panels.append(_panel_to_rich(spec))

            if not left_panels:
                # Guardrail: never show empty dashboard; fallback to useful defaults.
                for panel_type in ("task_queue", "task_detail", "event_stream"):
                    spec = self._get_spec(panel_type)
                    fn = self._panel_registry.get(panel_type)
                    if fn is not None:
                        left_panels.append(_panel_to_rich(spec))
            if not right_panels:
                for panel_type in ("model_io", "scorer_explain", "failures"):
                    spec = self._get_spec(panel_type)
                    fn = self._panel_registry.get(panel_type)
                    if fn is not None:
                        right_panels.append(_panel_to_rich(spec))

            left = Group(*left_panels)
            right = Group(*right_panels)
            board = Layout()
            board.split_row(
                Layout(left, name="left", ratio=1),
                Layout(right, name="right", ratio=1),
            )

            footer_bits = [
                "keys: p pause  f failed  r rerun  a/t group  m/s sort  v compact  b banner  x theme  u mode  e qa-expand",
                "cmd: task=<ids> agent=<ids> variant=<ids> status=<states> focus=<task_id> lock clear",
                "cmd+: /theme [contrast|quiet|research|research_redops|toggle] /banner [show|hide|toggle] /mode [auto|default|qa_dense|ops_dense|compare_dense] /qa [expand|collapse|toggle]",
                "input: press '/' then type command and Enter; Tab complete; ↑↓ history",
                "example: /task t1   then   /status error",
            ]
            if self._controller is not None and getattr(self._controller, "last_feedback", ""):
                footer_bits.append(f"feedback: {self._controller.last_feedback}")
            if self._controller is not None:
                cmd_buf = str(getattr(self._controller, "command_buffer", "") or "")
                cmd_mode = bool(getattr(self._controller, "command_mode", False))
                if cmd_mode or cmd_buf:
                    cursor = "▌" if cmd_mode else ""
                    footer_bits.append(f"command> {cmd_buf}{cursor}")
                suggestions = list(getattr(self._controller, "command_suggestions", []) or [])
                if cmd_mode and suggestions:
                    footer_bits.append(f"suggest: {' '.join(suggestions[:5])}")
            if self._controller is not None and getattr(self._controller, "show_help", False):
                footer_bits.append("help: Tab/Shift+Tab panel | j/k task | Enter lock focus | /task /agent /variant /status /focus /rerun failed /explain")
            if self._latest_summary:
                footer_bits.append(self._latest_summary)
            footer = Panel(
                Group(*[Text(x, style=tokens.panel_text) for x in footer_bits]),
                border_style=tokens.accent,
                box=(box.MINIMAL if self._active_theme_mode() == "quiet" else box.SQUARE),
                padding=(0, 1),
            )

            layout = Layout()
            top_size = max(3, min(6, len(banner_lines) + 1))
            kpi_size = 3
            overview_size = 7
            bottom_size = max(3, min(6, len(footer_bits) + 1))
            layout.split_column(
                Layout(name="top", size=top_size),
                Layout(name="kpi", size=kpi_size),
                Layout(name="overview", size=overview_size),
                Layout(name="main", ratio=1),
                Layout(name="bottom", size=bottom_size),
            )
            layout["top"].update(top_bar)
            layout["kpi"].update(kpi_panel)
            layout["overview"].update(progress_panel)
            layout["main"].update(board)
            layout["bottom"].update(footer)
            if self._ansi_enabled:
                if self._rich_live is None:
                    self._rich_live = Live(
                        layout,
                        console=console,
                        auto_refresh=False,
                        screen=True,
                        transient=False,
                    )
                    self._rich_live.start()
                else:
                    self._rich_live.update(layout, refresh=False)
                self._rich_live.refresh()
            else:
                console.print(layout)

    def render_plan(self, plan: Any) -> None:
        super().render_plan(plan)
        self._plan_mode = str(getattr(plan, "mode", "single"))
        self._plan_counts = {
            "tasks": len(getattr(plan, "task_ids", []) or []),
            "agents": len(getattr(plan, "agent_ids", []) or []),
            "variants": len(getattr(plan, "variant_ids", []) or []),
            "trials": len(getattr(plan, "trials", []) or []),
        }
        trials = list(getattr(plan, "trials", []) or [])
        if trials:
            first_task = getattr(trials[0], "task", None)
            metadata = getattr(first_task, "metadata", {}) if first_task is not None else {}
            if isinstance(metadata, dict):
                bench = metadata.get("benchmark") or metadata.get("benchmark_name")
                if bench:
                    self._benchmark_name = str(bench)
        for tr in trials:
            if not hasattr(tr, "task_id") or not hasattr(tr, "agent_id"):
                continue
            sample = dict(getattr(tr, "sample", {}) or {})
            key = self._monitor_key(
                task_id=str(getattr(tr, "task_id")),
                agent_id=str(getattr(tr, "agent_id")),
                variant_id=str(getattr(tr, "variant_id", "default")),
                sample_id=(str(getattr(tr, "sample_id")) if getattr(tr, "sample_id", None) is not None else None),
            )
            self._task_monitor.upsert_queued(
                task_id=str(getattr(tr, "task_id")),
                agent_id=str(getattr(tr, "agent_id")),
                variant_id=str(getattr(tr, "variant_id", "default")),
                sample_id=(str(getattr(tr, "sample_id")) if getattr(tr, "sample_id", None) is not None else None),
            )
            self._trial_context[key] = {
                "input": sample.get("input"),
                "instruction": sample.get("instruction"),
                "target": sample.get("target"),
                "metadata": sample.get("metadata"),
            }
        self._latest_global["total"] = len(getattr(plan, "trials", []) or [])
        self._activity_label = "planned"
        self._events.append(f"{self._now()} [trial] plan mode={plan.mode} trials={len(plan.trials)}")
        self._events.append(
            "{ts} [runtime] ui.throttle refresh_interval_ms={refresh} max_events={events} max_failures={failures} max_active_trials={active}".format(
                ts=self._now(),
                refresh=int(self.refresh_interval_ms),
                events=int(self.max_events),
                failures=int(self.max_failures),
                active=int(self.max_active_trials),
            )
        )
        self._flush_dashboard(force=True)

    def render_global(self, *, done: int, total: int, success: int, incorrect: int, other: int) -> None:
        self._latest_global = {
            "done": int(done),
            "total": int(total),
            "success": int(success),
            "incorrect": int(incorrect),
            "other": int(other),
        }
        self._flush_dashboard()

    def render_trial_start(self, trial: Any, index: int, total: int) -> None:
        key = f"{trial.task_id}:{trial.agent_id}:{getattr(trial, 'variant_id', 'default')}:{trial.sample_id}"
        self._active[key] = (
            f"[{index}/{total}] task={trial.task_id} agent={trial.agent_id} "
            f"variant={getattr(trial, 'variant_id', 'default')} sample={trial.sample_id}"
        )
        while len(self._active) > max(1, int(self.max_active_trials)):
            oldest = next(iter(self._active.keys()))
            self._active.pop(oldest, None)
        normalized = normalize_ui_event(
            {
                "event": "runtime.trial.start",
                "task_id": trial.task_id,
                "agent_id": trial.agent_id,
                "variant_id": getattr(trial, "variant_id", "default"),
                "sample_id": trial.sample_id,
            },
            run_id=self._run_id,
            ts_ms=int(time.time() * 1000),
        )
        self._task_monitor.apply_event(normalized)
        self._events.append(f"{self._now()} [trial] start {key}")
        self._activity_label = "trial-running"
        self._last_event_wall = time.monotonic()
        self._flush_dashboard()

    def render_trial_finish(self, outcome: Any) -> None:
        tr = outcome.task_result
        key_prefix = f"{tr.task_id}:{tr.agent_id}:{(tr.payload or {}).get('variant_id', 'default')}:{tr.sample_id}"
        monitor_key = self._monitor_key(
            task_id=str(tr.task_id),
            agent_id=str(tr.agent_id),
            variant_id=str((tr.payload or {}).get("variant_id", "default")),
            sample_id=(str(tr.sample_id) if tr.sample_id is not None else None),
        )
        self._active.pop(key_prefix, None)
        status = tr.status.value
        self._events.append(f"{self._now()} [trial] finish {key_prefix} status={status}")
        if status in {"error", "incorrect", "limit_exceeded", "cancelled"}:
            self._failures.append(f"{key_prefix} status={status}")
        self._activity_label = "trial-finished"
        self._last_event_wall = time.monotonic()
        normalized = normalize_ui_event(
            {
                "event": "runtime.trial.finish",
                "task_id": tr.task_id,
                "agent_id": tr.agent_id,
                "variant_id": (tr.payload or {}).get("variant_id", "default"),
                "sample_id": tr.sample_id,
                "status": status,
            },
            run_id=self._run_id,
            ts_ms=int(time.time() * 1000),
        )
        self._task_monitor.apply_event(normalized)
        final_output = getattr(tr, "final_output", {}) or {}
        content = final_output.get("content")
        ctx = self._trial_context.setdefault(monitor_key, {})
        if content is not None:
            ctx["output_content"] = str(content)
        if content is not None:
            self._events.append(f"{self._now()} [agent] model_io content={str(content)[:200]}")
        if getattr(outcome, "scores", None):
            score_chunks = []
            score_lines: list[str] = []
            judge_json: Any = None
            for name, score in sorted(getattr(outcome, "scores").items()):
                val = getattr(score, "value", 0.0)
                try:
                    val_f = float(val)
                except Exception:
                    val_f = 0.0
                self._metric_sum[name] = float(self._metric_sum.get(name, 0.0)) + val_f
                self._metric_count[name] = int(self._metric_count.get(name, 0)) + 1
                self._metric_last[name] = val_f
                exp = str(getattr(score, "explanation", "") or "").strip()
                metadata = dict(getattr(score, "metadata", {}) or {})
                if judge_json is None:
                    for key in ("judge_parsed", "judge_json", "judge_raw_json", "judge_result"):
                        if key in metadata and metadata.get(key) is not None:
                            judge_json = metadata.get(key)
                            break
                score_lines.append(f"{name}={val_f:.3f}" + (f" ({exp[:80]})" if exp else ""))
                if exp:
                    score_chunks.append(f"{name}={val_f:.3f} reason={exp[:140]}")
                else:
                    score_chunks.append(f"{name}={val_f:.3f}")
            if score_chunks:
                self._events.append(f"{self._now()} [scorer] explanations={' '.join(score_chunks)}")
            ctx["score_lines"] = score_lines
            if score_lines:
                try:
                    ctx["final_score"] = getattr(next(iter(getattr(outcome, "scores").values())), "value", None)
                except Exception:
                    pass
            if judge_json is not None:
                ctx["judge_json"] = judge_json
        self._flush_dashboard()

    def render_compare(self, aggregate: Any) -> None:
        by_task_agent = getattr(aggregate, "by_task_agent", {}) or {}
        focus_metric = self._configured_primary_metric_name()
        rows: list[dict[str, Any]] = []
        for key in sorted(by_task_agent.keys()):
            row = by_task_agent[key]
            task_id = str(row.get("task_id"))
            agent_id = str(row.get("agent_id"))
            variant_id = str(row.get("variant_id") or "default")
            if self._controller and not self._controller.should_display(
                task_id=task_id,
                agent_id=agent_id,
                variant_id=variant_id,
            ):
                continue
            metrics = dict(row.get("metrics") or {})
            if focus_metric and focus_metric in metrics:
                metric_score = float(metrics.get(focus_metric) or 0.0)
            else:
                metric_score = 0.0 if not metrics else max(float(v) for v in metrics.values())
            failures = int((row.get("status_counts") or {}).get("error", 0))
            model = str(row.get("model") or "-")
            label = f"{task_id}/{agent_id}#{variant_id}@{model}"
            rows.append(
                {
                    "label": label,
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "variant_id": variant_id,
                    "model": model,
                    "focus_score": metric_score,
                    "metric_text": ", ".join(f"{k}={v:.3f}" for k, v in sorted(metrics.items())),
                    "failures": failures,
                }
            )

        sort_mode = self._controller.compare_sort if self._controller else "metric"
        if sort_mode == "status":
            rows.sort(key=lambda x: (x["failures"], -x["focus_score"], x["label"]))
        else:
            rows.sort(key=lambda x: (-x["focus_score"], x["failures"], x["label"]))

        current_rank: dict[str, int] = {}
        display: list[str] = []
        grouped: dict[str, list[str]] = {}
        leaders: list[str] = []
        for idx, entry in enumerate(rows, start=1):
            label = str(entry["label"])
            score = float(entry["focus_score"])
            metric_text = str(entry["metric_text"])
            failures = int(entry["failures"])
            current_rank[label] = idx
            prev = self._compare_ranks.get(label)
            if prev is None:
                delta = "✨new"
            else:
                diff = prev - idx
                if diff > 0:
                    delta = f"⬆️{diff:+d}"
                elif diff < 0:
                    delta = f"⬇️{diff:+d}"
                else:
                    delta = "➖0"
            variant_id = str(entry["variant_id"])
            row_text = (
                f"rank={idx} ({delta}) label={label} "
                f"focus={focus_metric or 'best'}={score:.3f} failures={failures} metrics=[{metric_text}]"
            )
            display.append(row_text)
            grouped.setdefault(variant_id, []).append(row_text)
            if len(leaders) < 5:
                leaders.append(f"#{idx} {label} {score:.3f} ({delta})")
        self._compare_rows = display
        self._compare_rows_by_variant = grouped
        self._compare_ranks = current_rank
        self._compare_focus_metric = focus_metric
        self._compare_leader_rows = leaders
        self._flush_dashboard()

    def render_controls(self) -> None:
        if not self.verbose:
            return
        if self._rich_enabled:
            # Rich layout already includes a controls panel; avoid duplicate plain-text block.
            return
        self._emit("")
        self._emit("=== Controls ===")
        self._emit("keys: p pause/resume | f failed-focus | r rerun-failed | a/t group | m/s sort | v compact | b banner | x theme | u mode | e qa-expand | Tab j/k/up/down Enter ?")
        self._emit("palette: /task /agent /variant /status /focus /rerun failed /explain /theme[contrast|quiet|research|research_redops] /banner /mode /qa /help /clear  (Tab complete, ↑↓ history)")

    def render_summary(self, summary: Any, artifacts_dir: str, rerun_cmd: str) -> None:
        self._latest_summary = (
            "total={total} success={success} incorrect={incorrect} error={error} limit_exceeded={limit} cancelled={cancelled}".format(
                total=summary.total,
                success=summary.success,
                incorrect=summary.incorrect,
                error=summary.error,
                limit=summary.limit_exceeded,
                cancelled=summary.cancelled,
            )
        )
        self._events.append(f"{self._now()} [runtime] summary ready")
        self._flush_dashboard(force=True)
        if self._rich_live is not None:
            try:
                self._rich_live.stop()
            except Exception:
                pass
            self._rich_live = None
        super().render_summary(summary, artifacts_dir, rerun_cmd)

    def render_runtime_event(self, event: dict[str, Any]) -> None:
        if not self.verbose:
            return
        if event.get("run_id"):
            self._run_id = str(event.get("run_id"))
        ts_ms_raw = event.get("ts_ms")
        ts_ms = int(ts_ms_raw) if isinstance(ts_ms_raw, (int, float)) else int(time.time() * 1000)
        normalized = normalize_ui_event(
            event,
            run_id=self._run_id,
            ts_ms=ts_ms,
            default_task_id=(str(event.get("task_id")) if event.get("task_id") is not None else None),
            default_agent_id=(str(event.get("agent_id")) if event.get("agent_id") is not None else None),
            default_variant_id=(str(event.get("variant_id")) if event.get("variant_id") is not None else "default"),
        )
        self._task_monitor.apply_event(normalized)
        name = str(normalized.event)
        payload_obj = normalized.payload if isinstance(normalized.payload, dict) else {}
        self._runtime_events.append(
            {
                "time": datetime.fromtimestamp(normalized.ts_ms / 1000.0, timezone.utc).strftime("%H:%M:%S"),
                "event": name,
                "phase": str(normalized.phase.value),
                "task_id": normalized.task_id,
                "agent_id": normalized.agent_id,
                "variant_id": normalized.variant_id,
                "message": normalized.message,
                "payload": payload_obj,
            }
        )
        self._last_event_wall = time.monotonic()
        if name == "runtime.model.query.start":
            self._inflight_model_queries += 1
            self._activity_label = "querying-model"
        elif name in {"runtime.model.query.finish", "runtime.model.query.error"}:
            self._inflight_model_queries = max(0, self._inflight_model_queries - 1)
            self._activity_label = "agent-running" if self._inflight_model_queries > 0 else "agent-wait"
        elif name == "runtime.scorer.start":
            self._inflight_scorers += 1
            self._activity_label = "scoring"
        elif name == "runtime.scorer.finish":
            self._inflight_scorers = max(0, self._inflight_scorers - 1)
            self._activity_label = "trial-finishing"
        elif name == "runtime.trial.start":
            self._activity_label = "trial-running"
        elif name == "runtime.trial.finish":
            self._activity_label = "trial-finished"
        elif name == "runtime.env.command.start":
            self._inflight_env_commands += 1
            self._activity_label = "docker-command-running"
        elif name in {"runtime.env.command.stdout", "runtime.env.command.stderr"}:
            chunk = payload_obj.get("chunk")
            if isinstance(chunk, str) and chunk.strip():
                self._env_stream_chunks += 1
            self._activity_label = "docker-streaming"
        elif name in {"runtime.env.command.finish", "runtime.env.command.timeout"}:
            self._inflight_env_commands = max(0, self._inflight_env_commands - 1)
            self._activity_label = "docker-command-finished"
        elif "container.starting" in name:
            self._activity_label = "docker-compose-building"
        elif "container.started" in name:
            ec = payload_obj.get("exit_code")
            self._activity_label = "container-ready" if ec == 0 else "container-build-failed"
        elif "container.stopping" in name:
            self._activity_label = "container-stopping"
        elif "container.stopped" in name:
            self._activity_label = "container-stopped"
        elif name == "ui.heartbeat":
            self._activity_label = "running"
            self._flush_dashboard()
            return
        elif name == "ui.control":
            msg = str(normalized.message or "")
            if "interactive stdin input enabled" in msg:
                self._input_status = "tty:on"
            elif "interactive stdin input disabled" in msg:
                self._input_status = "tty:off"
        tag = self._phase_tag(name)
        raw = normalized.to_dict()
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        def _pick(key: str) -> Any:
            value = raw.get(key)
            if value is None:
                value = payload.get(key)
            if value is None:
                nested = payload.get("payload")
                if isinstance(nested, dict):
                    value = nested.get(key)
            return value

        def _clip(value: Any, *, limit: int = 180) -> str:
            text = str(value).replace("\n", "\\n")
            return text if len(text) <= limit else text[: limit - 1] + "…"

        details = []
        for key in (
            "task_id",
            "agent_id",
            "variant_id",
            "model",
            "base_url",
            "project",
            "compose_file",
            "image",
            "service",
            "command_text",
            "exit_code",
            "duration_ms",
            "ready",
            "status",
            "score",
            "message",
            "stdout_tail",
            "stderr_tail",
        ):
            value = _pick(key)
            if value is not None:
                details.append(f"{key}={_clip(value)}")
        suffix = (" " + " ".join(details)) if details else ""
        line = f"{self._now()} [{tag}] {name}{suffix}"
        self._events.append(line)
        if name in {"runtime.model.query.start", "runtime.model.query.error", "runtime.model.io"}:
            for extra_line in self._model_debug_lines(raw, prefix=f"{self._now()} [{tag}]"):
                self._events.append(extra_line)

        model_value = _pick("model")
        if isinstance(model_value, str) and model_value.strip():
            self._model_name = model_value.strip()
        base_value = _pick("base_url")
        if isinstance(base_value, str) and base_value.strip():
            self._model_base_url = base_value.strip()
        self._flush_dashboard()
