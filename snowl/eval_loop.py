"""Internal single-trial eval lifecycle helper.

This module keeps the current eval-loop behavior intact while moving the
per-trial lifecycle out of ``snowl.eval``. It is not a public scheduler API.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from snowl.core import Scorer, ToolSpec
from snowl.observability.events import RunEventBus
from snowl.planning import PlanTrial, trial_key as make_trial_key
from snowl.runtime import TrialOutcome, TrialRequest
from snowl.runtime.container_lifecycle import RuntimeContainerLifecycleManager
from snowl.runtime.engine import finalize_trial_phase, prepare_trial_phase, execute_agent_phase, score_trial_phase
from snowl.runtime.recovery import RecoveryManager, attempt_is_success
from snowl.runtime.resource_scheduler import ResourceScheduler
from snowl.ui.contracts import TaskMonitor, normalize_ui_event


@dataclass(frozen=True)
class EvalTrialRunResult:
    trial_index: int
    trial: PlanTrial
    outcome: TrialOutcome
    attempt_row: dict[str, Any]


class EvalTrialLifecycle:
    """Run one trial attempt and persist its side effects.

    This owns TrialRequest construction, runtime event normalization,
    checkpoint/recovery writes, and retry-recovered events. Queue admission and
    retry scheduling stay in ``snowl.eval``.
    """

    def __init__(
        self,
        *,
        run_id: str,
        base_dir: Path,
        checkpoint_key: str,
        checkpoint: dict[str, Any],
        checkpoint_lock: asyncio.Lock,
        resume: bool,
        retry_mode: bool,
        display_total: int,
        scorer: Scorer,
        tool_specs: list[ToolSpec],
        shared_sandbox_runtime: Any | None,
        container_lifecycle: RuntimeContainerLifecycleManager,
        scheduler: ResourceScheduler,
        task_monitor: TaskMonitor,
        renderer: Any | None,
        event_bus: RunEventBus,
        recovery_manager: RecoveryManager,
        effective_rows: dict[str, dict[str, Any]],
        effective_outcomes_by_key: dict[str, TrialOutcome],
        outcomes: list[TrialOutcome],
        completed: dict[str, Any],
        log: Callable[[str], None],
        save_checkpoint: Callable[[Path, str, dict[str, Any]], None],
        serialize_outcome: Callable[[TrialOutcome], dict[str, Any]],
    ) -> None:
        self.run_id = run_id
        self.base_dir = base_dir
        self.checkpoint_key = checkpoint_key
        self.checkpoint = checkpoint
        self.checkpoint_lock = checkpoint_lock
        self.resume = resume
        self.retry_mode = retry_mode
        self.display_total = display_total
        self.scorer = scorer
        self.tool_specs = tool_specs
        self.shared_sandbox_runtime = shared_sandbox_runtime
        self.container_lifecycle = container_lifecycle
        self.scheduler = scheduler
        self.task_monitor = task_monitor
        self.renderer = renderer
        self.event_bus = event_bus
        self.recovery_manager = recovery_manager
        self.effective_rows = effective_rows
        self.effective_outcomes_by_key = effective_outcomes_by_key
        self.outcomes = outcomes
        self.completed = completed
        self.log = log
        self.save_checkpoint = save_checkpoint
        self.serialize_outcome = serialize_outcome

    async def run(
        self,
        trial_index: int,
        trial: PlanTrial,
        *,
        retry_source: str = "initial_run",
    ) -> EvalTrialRunResult:
        key = make_trial_key(trial)
        if self.resume and not self.retry_mode:
            async with self.checkpoint_lock:
                self.checkpoint["in_progress"][key] = {
                    "task_id": trial.task_id,
                    "agent_id": trial.agent_id,
                    "sample_id": trial.sample_id,
                    "started_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                }
                self.save_checkpoint(self.base_dir, self.checkpoint_key, self.checkpoint)

        if self.renderer:
            self.renderer.render_trial_start(trial, trial_index, self.display_total)
        self.log(
            f"trial_start idx={trial_index}/{self.display_total} task={trial.task_id} agent={trial.agent_id} variant={trial.variant_id} sample={trial.sample_id} retry_source={retry_source}"
        )
        if retry_source != "initial_run":
            self._emit_retry_start(trial=trial, retry_source=retry_source)

        request = TrialRequest(
            task=trial.task,
            agent=trial.agent,
            scorer=self.scorer,
            sample=trial.sample,
            tools=self.tool_specs,
            sandbox_runtime=self.shared_sandbox_runtime,
            on_event=lambda event: self._on_runtime_event(event, trial=trial),
            container_lifecycle=self.container_lifecycle,
            run_id=self.run_id,
            trial_id=key,
        )
        async with self.scheduler.running_trial_slot():
            prepared = await prepare_trial_phase(request)
            partial = await execute_agent_phase(prepared)
        async with self.scheduler.scoring_slot():
            outcome = await score_trial_phase(prepared, partial)
        outcome, _ = await finalize_trial_phase(prepared, outcome)

        async with self.checkpoint_lock:
            attempt_row = self.recovery_manager.record_attempt(
                effective_rows=self.effective_rows,
                key=key,
                trial=trial,
                outcome=outcome,
                retry_source=retry_source,
                current_effective_outcomes=self.effective_outcomes_by_key,
            )
            self.outcomes.clear()
            self.outcomes.extend(list(self.effective_outcomes_by_key.values()))
            self.recovery_manager.write()
            if self.resume and not self.retry_mode:
                self.completed[key] = self.serialize_outcome(self.effective_outcomes_by_key[key])
                self.checkpoint["completed"] = self.completed
                self.checkpoint["in_progress"].pop(key, None)
                self.checkpoint["failed_keys"] = sorted(
                    k
                    for k, v in self.completed.items()
                    if v.get("task_result", {}).get("status")
                    in {"error", "limit_exceeded", "cancelled", "incorrect"}
                )
                self.save_checkpoint(self.base_dir, self.checkpoint_key, self.checkpoint)

        if retry_source != "initial_run" and attempt_is_success(outcome):
            self._emit_recovered(trial=trial, retry_source=retry_source, attempt_row=attempt_row)

        if self.resume and not self.retry_mode:
            async with self.checkpoint_lock:
                self.checkpoint["in_progress"].pop(key, None)
                self.save_checkpoint(self.base_dir, self.checkpoint_key, self.checkpoint)
        return EvalTrialRunResult(
            trial_index=trial_index,
            trial=trial,
            outcome=outcome,
            attempt_row=attempt_row,
        )

    def _record_event(self, row: dict[str, Any], *, trial: PlanTrial | None = None) -> dict[str, Any]:
        persisted_rows = self.event_bus.append(row, trial=trial)
        return persisted_rows[0]

    def _render_runtime_event(self, event: dict[str, Any]) -> None:
        if self.renderer and hasattr(self.renderer, "render_runtime_event"):
            self.renderer.render_runtime_event(event)

    def _emit_retry_start(self, *, trial: PlanTrial, retry_source: str) -> None:
        retry_evt = normalize_ui_event(
            {
                "event": "runtime.trial.retry.start",
                "message": f"{retry_source} attempt started",
                "retry_source": retry_source,
                "task_id": trial.task_id,
                "agent_id": trial.agent_id,
                "variant_id": trial.variant_id,
                "sample_id": trial.sample_id,
            },
            run_id=self.run_id,
            ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ).to_dict()
        self._record_event(retry_evt, trial=trial)
        self._render_runtime_event(retry_evt)

    def _emit_recovered(
        self,
        *,
        trial: PlanTrial,
        retry_source: str,
        attempt_row: dict[str, Any],
    ) -> None:
        recovered_evt = normalize_ui_event(
            {
                "event": "runtime.trial.recovered",
                "message": f"{retry_source} recovered trial",
                "retry_source": retry_source,
                "attempt_no": attempt_row.get("attempt_no"),
                "task_id": trial.task_id,
                "agent_id": trial.agent_id,
                "variant_id": trial.variant_id,
                "sample_id": trial.sample_id,
            },
            run_id=self.run_id,
            ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        ).to_dict()
        self._record_event(recovered_evt, trial=trial)
        self._render_runtime_event(recovered_evt)

    def _on_runtime_event(self, event: dict[str, Any], *, trial: PlanTrial) -> None:
        raw = dict(event or {})
        normalized = normalize_ui_event(
            raw,
            run_id=self.run_id,
            ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
            default_task_id=trial.task_id,
            default_agent_id=trial.agent_id,
            default_variant_id=trial.variant_id,
        )
        self.task_monitor.apply_event(normalized)
        evt = normalized.to_dict()
        persisted_evt = self._record_event(evt, trial=trial)
        self.log(f"event {json.dumps(persisted_evt, ensure_ascii=False)}")
        self._render_runtime_event(evt)
