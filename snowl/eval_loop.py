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
from snowl.runtime.container_contract import resolve_runtime_container_spec
from snowl.runtime.container_lifecycle import RuntimeContainerLifecycleManager
from snowl.runtime.engine import finalize_trial_phase, prepare_trial_phase, execute_agent_phase, score_trial_phase
from snowl.runtime.recovery import RecoveryManager, attempt_is_success
from snowl.runtime.resource_scheduler import ResourceScheduler, TaskExecutionPlan, TrialDescriptor
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
        scorer: Scorer | None = None,
        scorers: tuple[Scorer, ...] = (),
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
        bridge: dict[str, Any] | None = None,
        epochs: int = 1,
        score_reducer: Any | None = None,
        model_client: Any | None = None,
    ) -> None:
        self.run_id = run_id
        self.base_dir = base_dir
        self.checkpoint_key = checkpoint_key
        self.checkpoint = checkpoint
        self.checkpoint_lock = checkpoint_lock
        self.resume = resume
        self.retry_mode = retry_mode
        self.display_total = display_total
        # Backward compat: single scorer wraps into tuple
        if scorers:
            self.scorers = scorers
        elif scorer is not None:
            self.scorers = (scorer,)
        else:
            self.scorers = ()
        self.scorer = self.scorers[0] if self.scorers else scorer
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
        self._bridge = bridge
        self._epochs = epochs
        self._score_reducer = score_reducer
        self._model_client = model_client

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

        container_spec = resolve_runtime_container_spec(
            task_metadata=trial.task.metadata,
            sample=trial.sample,
        )
        trial_descriptor = TrialDescriptor(
            trial_id=key,
            task_id=trial.task_id,
            sample_id=trial.sample_id,
            agent_id=trial.agent_id,
            variant_id=trial.variant_id,
            scorer_id=getattr(self.scorer, "scorer_id", None) if self.scorer else None,
            seed=None,
            spec_hash=container_spec.spec_hash,
            provider_ids=(),
        )
        execution_plan = TaskExecutionPlan(
            trial=trial_descriptor,
            requires_container=bool(container_spec.requires_container),
            requires_prepare=True,
            requires_build=False,
            estimated_prepare_cost="container" if container_spec.requires_container else "light",
            spec_hash=container_spec.spec_hash,
        )
        # Build per-trial middleware_config: agent-level config + sample-level overrides
        agent_middleware = dict(getattr(trial.agent, "middleware_config", {}) or {})
        sample_meta = trial.sample.get("metadata", {}) if isinstance(trial.sample, dict) else {}
        per_sample_injection = sample_meta.get("injection_config", {})
        if per_sample_injection:
            agent_middleware["injection_config"] = per_sample_injection

        request = TrialRequest(
            task=trial.task,
            agent=trial.agent,
            scorer=self.scorer,
            scorers=self.scorers,
            sample=trial.sample,
            tools=self.tool_specs,
            sandbox_runtime=self.shared_sandbox_runtime,
            on_event=lambda event: self._on_runtime_event(event, trial=trial),
            execution_plan=execution_plan,
            trial_descriptor=trial_descriptor,
            container_lifecycle=self.container_lifecycle,
            run_id=self.run_id,
            trial_id=key,
            middleware_config=agent_middleware,
            epochs=getattr(self, '_epochs', 1),
            score_reducer=getattr(self, '_score_reducer', None),
        )
        async with self.scheduler.begin_prepare(execution_plan):
            prepared = await prepare_trial_phase(request)

        # Activate bridge mode if configured
        bridge_token = None
        bridge_usage_token = None
        bridge_accumulator = None
        bridge_cfg = self._bridge
        if bridge_cfg and bridge_cfg.get("enabled") and self._model_client is not None:
            try:
                from snowl.bridges._config import BridgeConfig, set_bridge_config, set_usage_accumulator, BridgeUsageAccumulator
                from snowl.bridges._patch_openai import patch_openai
                from snowl.bridges._patch_anthropic import patch_anthropic

                if bridge_cfg.get("patch_openai", True):
                    patch_openai()
                if bridge_cfg.get("patch_anthropic", True):
                    patch_anthropic()

                config = BridgeConfig(
                    enabled=True,
                    model_client=self._model_client,
                    provider_id="eval_bridge",
                )
                bridge_token = set_bridge_config(config)
                bridge_accumulator = BridgeUsageAccumulator()
                bridge_usage_token = set_usage_accumulator(bridge_accumulator)
            except ImportError:
                pass

        try:
            async with self.scheduler.begin_execute(execution_plan):
                partial = await execute_agent_phase(prepared)
        finally:
            # Deactivate bridge mode
            if bridge_token is not None:
                try:
                    from snowl.bridges._config import reset_bridge_config, reset_usage_accumulator
                    reset_bridge_config(bridge_token)
                    if bridge_usage_token is not None:
                        reset_usage_accumulator(bridge_usage_token)
                except ImportError:
                    pass

                # Merge bridge usage into task result
                if bridge_accumulator is not None and partial is not None:
                    try:
                        tr = partial.task_result
                        existing = tr.usage or {}
                        tr.usage = {
                            "input_tokens": (existing.get("input_tokens") or 0) + bridge_accumulator.input_tokens,
                            "output_tokens": (existing.get("output_tokens") or 0) + bridge_accumulator.output_tokens,
                            "total_tokens": (existing.get("total_tokens") or 0) + bridge_accumulator.total_tokens,
                            "bridge_calls": bridge_accumulator.call_count,
                        }
                    except Exception:
                        pass
        async with self.scheduler.begin_score(execution_plan):
            outcome = await score_trial_phase(prepared, partial)

        # Multi-epoch: collect scores from additional epochs and reduce
        epochs = request.epochs
        if epochs > 1 and request.score_reducer is not None:
            epoch_scores = [outcome.scores]
            for epoch_idx in range(1, epochs):
                async with self.scheduler.begin_prepare(execution_plan):
                    prepared = await prepare_trial_phase(request)
                async with self.scheduler.begin_execute(execution_plan):
                    partial = await execute_agent_phase(prepared)
                async with self.scheduler.begin_score(execution_plan):
                    epoch_outcome = await score_trial_phase(prepared, partial)
                async with self.scheduler.begin_finalize(execution_plan):
                    await finalize_trial_phase(prepared, epoch_outcome)
                epoch_scores.append(epoch_outcome.scores)
            reduced_scores = request.score_reducer.reduce(epoch_scores)
            outcome = TrialOutcome(
                task_result=outcome.task_result,
                scores=reduced_scores,
                trace=outcome.trace,
            )

        async with self.scheduler.begin_finalize(execution_plan):
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
