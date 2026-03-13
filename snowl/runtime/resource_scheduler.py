"""Runtime quota and admission primitives (running/scoring/container/build/provider) with instrumentation snapshots.

Framework role:
- Defines budget controls and semaphores used to throttle local concurrency and provider pressure.
- Provides phase/budget statistics used in profiling outputs and runtime diagnostics.

Runtime/usage wiring:
- Provider admission is consumed by model clients via slot resolvers; dispatch ordering is still controlled in `snowl.eval`.
- Expose phase APIs (`begin_prepare`, `begin_finalize`) that may be partially wired depending on eval-loop usage.
- Key top-level symbols in this file: `TrialDescriptor`, `TaskExecutionPlan`, `PhaseBudgetSnapshot`, `ResourceLimits`, `ResourceScheduler`, `_ScheduledSandboxRuntime`.

Change guardrails:
- Changing defaults or admission semantics here requires confirming where those APIs are actually invoked from eval paths.
- Prefer additive metrics changes; profiling consumers rely on stable field names.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from snowl.envs.sandbox_runtime import PreparedSandbox, SandboxRuntime


@dataclass(frozen=True)
class TrialDescriptor:
    trial_id: str
    task_id: str
    sample_id: str | None
    agent_id: str
    variant_id: str | None
    scorer_id: str | None
    seed: int | None
    spec_hash: str | None
    provider_ids: tuple[str, ...]
    phase: str = "PENDING"
    retry_count: int = 0


@dataclass(frozen=True)
class TaskExecutionPlan:
    trial: TrialDescriptor
    requires_container: bool = False
    requires_prepare: bool = False
    requires_build: bool = False
    estimated_agent_model_calls: int = 0
    estimated_judge_model_calls: int = 0
    estimated_total_model_calls: int = 0
    estimated_steps: int = 0
    estimated_duration_class: str = "light"
    estimated_prepare_cost: str = "none"
    provider_ids: tuple[str, ...] = ()
    spec_hash: str | None = None
    priority: float = 0.0


@dataclass(frozen=True)
class PhaseBudgetSnapshot:
    active: dict[str, int]
    queue_wait_ms: dict[str, Any]
    phase_duration_ms: dict[str, int]
    provider_inflight: dict[str, int]
    provider_utilization: dict[str, float]
    queue_depths: dict[str, int]


@dataclass(frozen=True)
class ResourceLimits:
    max_running_trials: int | None
    max_container_slots: int | None
    max_builds: int | None
    max_scoring_tasks: int | None
    provider_budgets: dict[str, int]


class ResourceScheduler:
    def __init__(
        self,
        *,
        max_running_trials: int | None = None,
        max_container_slots: int | None = None,
        max_builds: int | None = None,
        max_scoring_tasks: int | None = None,
        provider_budgets: dict[str, int] | None = None,
        max_trials: int | None = None,
        max_sandboxes: int | None = None,
        max_model_calls: int | None = None,
    ) -> None:
        running_limit = _normalize_limit(max_running_trials if max_running_trials is not None else max_trials)
        container_limit = _normalize_limit(max_container_slots if max_container_slots is not None else max_sandboxes)
        scoring_limit = _normalize_limit(max_scoring_tasks)
        provider_limit_map = {
            str(k).strip() or "default": _normalize_required_limit(v)
            for k, v in dict(provider_budgets or {}).items()
        }
        if not provider_limit_map and max_model_calls is not None:
            provider_limit_map["default"] = _normalize_required_limit(max_model_calls)
        self._limits = ResourceLimits(
            max_running_trials=running_limit,
            max_container_slots=container_limit,
            max_builds=_normalize_limit(max_builds),
            max_scoring_tasks=scoring_limit,
            provider_budgets=provider_limit_map,
        )
        self._running_sem: asyncio.Semaphore | None = None
        self._running_loop: asyncio.AbstractEventLoop | None = None
        self._container_sem: asyncio.Semaphore | None = None
        self._container_loop: asyncio.AbstractEventLoop | None = None
        self._scoring_sem: asyncio.Semaphore | None = None
        self._scoring_loop: asyncio.AbstractEventLoop | None = None
        self._provider_sems: dict[tuple[int, str], asyncio.Semaphore] = {}
        self._provider_loop: asyncio.AbstractEventLoop | None = None
        self._build_sem: threading.BoundedSemaphore | None = (
            threading.BoundedSemaphore(self._limits.max_builds)
            if self._limits.max_builds is not None
            else None
        )
        self._stats_lock = threading.Lock()
        self._active = {
            "preparing": 0,
            "ready": 0,
            "executing": 0,
            "scoring": 0,
            "finalizing": 0,
            "running_trials": 0,
            "scoring_tasks": 0,
            "container_slots": 0,
            "builds": 0,
        }
        self._provider_inflight: dict[str, int] = {}
        self._queue_wait_totals: dict[str, float] = {
            "prepare": 0.0,
            "execute": 0.0,
            "score": 0.0,
            "finalize": 0.0,
            "running": 0.0,
            "scoring": 0.0,
            "container": 0.0,
        }
        self._queue_wait_counts: dict[str, int] = {
            "prepare": 0,
            "execute": 0,
            "score": 0,
            "finalize": 0,
            "running": 0,
            "scoring": 0,
            "container": 0,
        }
        self._phase_duration_totals: dict[str, float] = {
            "prepare": 0.0,
            "execute": 0.0,
            "score": 0.0,
            "finalize": 0.0,
        }
        self._phase_duration_counts: dict[str, int] = {
            "prepare": 0,
            "execute": 0,
            "score": 0,
            "finalize": 0,
        }
        self._provider_queue_wait_totals: dict[str, float] = {}
        self._provider_queue_wait_counts: dict[str, int] = {}
        self._queue_depths: dict[str, int] = {
            "prepare": 0,
            "ready": 0,
            "recovery": 0,
            "score": 0,
            "finalize": 0,
        }

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    def controls(self) -> dict[str, Any]:
        provider_budgets = dict(self._limits.provider_budgets)
        legacy_model_calls = max(provider_budgets.values()) if provider_budgets else None
        return {
            "max_running_trials": self._limits.max_running_trials,
            "max_container_slots": self._limits.max_container_slots,
            "max_builds": self._limits.max_builds,
            "max_scoring_tasks": self._limits.max_scoring_tasks,
            "provider_budgets": provider_budgets,
            "max_trials": self._limits.max_running_trials,
            "max_sandboxes": self._limits.max_container_slots,
            "max_model_calls": legacy_model_calls,
        }

    def stats_snapshot(self) -> dict[str, Any]:
        return self.phase_budget_snapshot().__dict__

    def phase_budget_snapshot(self) -> PhaseBudgetSnapshot:
        with self._stats_lock:
            provider_utilization = {
                provider_id: (
                    float(self._provider_inflight.get(provider_id, 0)) / float(limit)
                    if limit > 0
                    else 0.0
                )
                for provider_id, limit in self._limits.provider_budgets.items()
            }
            queue_wait_ms = {
                phase: int(total * 1000)
                for phase, total in self._queue_wait_totals.items()
            }
            provider_wait_ms = {
                provider_id: int(total * 1000)
                for provider_id, total in self._provider_queue_wait_totals.items()
            }
            phase_duration_ms = {
                phase: int(total * 1000)
                for phase, total in self._phase_duration_totals.items()
            }
            return PhaseBudgetSnapshot(
                active=dict(self._active),
                queue_wait_ms={**queue_wait_ms, "providers": provider_wait_ms},
                phase_duration_ms=phase_duration_ms,
                provider_inflight=dict(self._provider_inflight),
                provider_utilization=provider_utilization,
                queue_depths=dict(self._queue_depths),
            )

    def set_queue_depths(self, **depths: int) -> None:
        with self._stats_lock:
            for key, value in depths.items():
                self._queue_depths[str(key)] = max(0, int(value))

    def provider_headroom(self, provider_id: str | None) -> bool:
        key = str(provider_id or "default").strip() or "default"
        limit = self._limits.provider_budgets.get(key)
        if limit is None:
            return True
        with self._stats_lock:
            return self._provider_inflight.get(key, 0) < limit

    def phase_headroom(self, phase: str) -> bool:
        p = str(phase).strip().lower()
        with self._stats_lock:
            if p == "prepare":
                limit = self._limits.max_container_slots
                return limit is None or self._active["container_slots"] < limit
            if p == "execute":
                limit = self._limits.max_running_trials
                return limit is None or self._active["running_trials"] < limit
            if p == "score":
                limit = self._limits.max_scoring_tasks
                return limit is None or self._active["scoring_tasks"] < limit
            return True

    @asynccontextmanager
    async def begin_prepare(self, plan: TaskExecutionPlan | None = None) -> AsyncIterator[None]:
        # This API models prepare as its own admitted phase, but the current
        # repo-level eval loop does not call it directly for all prepare paths.
        needs_container = bool(plan.requires_container) if plan is not None else True
        sem = self._get_container_sem() if needs_container else None
        async with _AsyncSemaphoreContext(
            sem=sem,
            wait_phase="prepare" if needs_container else None,
            active_key="container_slots" if needs_container else None,
            phase_name="prepare",
            scheduler=self,
        ):
            yield None

    @asynccontextmanager
    async def begin_execute(self, plan: TaskExecutionPlan | None = None) -> AsyncIterator[None]:
        _ = plan
        sem = self._get_running_sem()
        async with _AsyncSemaphoreContext(
            sem=sem,
            wait_phase="execute",
            active_key="running_trials",
            phase_name="execute",
            scheduler=self,
        ):
            yield None

    @asynccontextmanager
    async def begin_score(self, plan: TaskExecutionPlan | None = None) -> AsyncIterator[None]:
        _ = plan
        sem = self._get_scoring_sem()
        async with _AsyncSemaphoreContext(
            sem=sem,
            wait_phase="score",
            active_key="scoring_tasks",
            phase_name="score",
            scheduler=self,
        ):
            yield None

    @asynccontextmanager
    async def begin_finalize(self, plan: TaskExecutionPlan | None = None) -> AsyncIterator[None]:
        _ = plan
        # Finalize is exposed for future phase-level control, but the current
        # main eval loop still skips explicit finalize admission.
        async with _AsyncSemaphoreContext(
            sem=None,
            wait_phase="finalize",
            active_key=None,
            phase_name="finalize",
            scheduler=self,
        ):
            yield None

    @asynccontextmanager
    async def provider_admission(self, provider_id: str | None, *, phase: str = "execute") -> AsyncIterator[None]:
        key = str(provider_id or "default").strip() or "default"
        # Provider budgets are enforced most directly when model calls happen,
        # not when the eval loop chooses which trial to dispatch next.
        sem = self._get_provider_sem(key)
        async with _AsyncSemaphoreContext(
            sem=sem,
            wait_phase=None,
            active_key=None,
            phase_name=str(phase or "execute").strip().lower() or "execute",
            scheduler=self,
            on_admission_acquire=lambda wait: self._record_provider_acquire(key, wait),
            on_admission_release=lambda hold: self._record_provider_release(key, hold),
        ):
            yield None

    @asynccontextmanager
    async def running_trial_slot(self) -> AsyncIterator[None]:
        async with self.begin_execute():
            yield None

    @asynccontextmanager
    async def scoring_slot(self) -> AsyncIterator[None]:
        async with self.begin_score():
            yield None

    @asynccontextmanager
    async def provider_slot(self, provider_id: str | None) -> AsyncIterator[None]:
        async with self.provider_admission(provider_id, phase="execute"):
            yield None

    @asynccontextmanager
    async def trial_slot(self) -> AsyncIterator[None]:
        async with self.running_trial_slot():
            yield None

    @asynccontextmanager
    async def model_call_slot(self) -> AsyncIterator[None]:
        async with self.provider_slot("default"):
            yield None

    def build_slot(self) -> _BuildSemaphoreContext:
        return _BuildSemaphoreContext(self._build_sem, scheduler=self)

    async def acquire_sandbox_slot(self) -> None:
        sem = self._get_container_sem()
        if sem is None:
            return
        start = time.perf_counter()
        await sem.acquire()
        self._record_phase_acquire("container", time.perf_counter() - start, active_key="container_slots")

    def release_sandbox_slot(self) -> None:
        sem = self._get_container_sem()
        if sem is None:
            return
        sem.release()
        self._record_phase_release(active_key="container_slots", hold_s=0.0, phase_name="prepare")

    def wrap_sandbox_runtime(self, inner: SandboxRuntime) -> SandboxRuntime:
        return _ScheduledSandboxRuntime(inner=inner, scheduler=self)

    def _get_running_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_running_trials is None:
            return None
        loop = asyncio.get_running_loop()
        if self._running_sem is None or self._running_loop is not loop:
            self._running_sem = asyncio.Semaphore(self._limits.max_running_trials)
            self._running_loop = loop
        return self._running_sem

    def _get_container_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_container_slots is None:
            return None
        loop = asyncio.get_running_loop()
        if self._container_sem is None or self._container_loop is not loop:
            self._container_sem = asyncio.Semaphore(self._limits.max_container_slots)
            self._container_loop = loop
        return self._container_sem

    def _get_scoring_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_scoring_tasks is None:
            return None
        loop = asyncio.get_running_loop()
        if self._scoring_sem is None or self._scoring_loop is not loop:
            self._scoring_sem = asyncio.Semaphore(self._limits.max_scoring_tasks)
            self._scoring_loop = loop
        return self._scoring_sem

    def _get_provider_sem(self, provider_id: str) -> asyncio.Semaphore | None:
        limit = self._limits.provider_budgets.get(provider_id)
        if limit is None:
            return None
        loop = asyncio.get_running_loop()
        loop_key = (id(loop), provider_id)
        if loop_key not in self._provider_sems:
            self._provider_sems[loop_key] = asyncio.Semaphore(limit)
            self._provider_loop = loop
        return self._provider_sems[loop_key]

    def _record_phase_acquire(self, phase: str, wait_s: float, *, active_key: str | None) -> None:
        with self._stats_lock:
            if phase:
                self._queue_wait_totals[phase] = self._queue_wait_totals.get(phase, 0.0) + max(0.0, float(wait_s))
                self._queue_wait_counts[phase] = self._queue_wait_counts.get(phase, 0) + 1
            if active_key:
                self._active[active_key] = self._active.get(active_key, 0) + 1

    def _record_phase_release(self, *, active_key: str | None, hold_s: float, phase_name: str | None) -> None:
        with self._stats_lock:
            if active_key:
                self._active[active_key] = max(0, self._active.get(active_key, 0) - 1)
            if phase_name:
                self._phase_duration_totals[phase_name] = self._phase_duration_totals.get(phase_name, 0.0) + max(
                    0.0, float(hold_s)
                )
                self._phase_duration_counts[phase_name] = self._phase_duration_counts.get(phase_name, 0) + 1

    def _record_provider_acquire(self, provider_id: str, wait_s: float) -> None:
        with self._stats_lock:
            self._provider_queue_wait_totals[provider_id] = self._provider_queue_wait_totals.get(provider_id, 0.0) + max(
                0.0, float(wait_s)
            )
            self._provider_queue_wait_counts[provider_id] = self._provider_queue_wait_counts.get(provider_id, 0) + 1
            self._provider_inflight[provider_id] = self._provider_inflight.get(provider_id, 0) + 1

    def _record_provider_release(self, provider_id: str, _hold: float) -> None:
        with self._stats_lock:
            self._provider_inflight[provider_id] = max(0, self._provider_inflight.get(provider_id, 0) - 1)


class _ScheduledSandboxRuntime:
    def __init__(self, *, inner: SandboxRuntime, scheduler: ResourceScheduler) -> None:
        self._inner = inner
        self._scheduler = scheduler

    async def prepare(self, spec) -> PreparedSandbox:  # type: ignore[no-untyped-def]
        await self._scheduler.acquire_sandbox_slot()
        try:
            return await self._inner.prepare(spec)
        except Exception:
            self._scheduler.release_sandbox_slot()
            raise

    async def run(self, prepared: PreparedSandbox, operation):  # type: ignore[no-untyped-def]
        return await self._inner.run(prepared, operation)

    async def teardown(self, prepared: PreparedSandbox) -> dict[str, Any]:
        try:
            return await self._inner.teardown(prepared)
        finally:
            self._scheduler.release_sandbox_slot()


class _BuildSemaphoreContext:
    def __init__(self, sem: threading.BoundedSemaphore | None, *, scheduler: ResourceScheduler | None = None) -> None:
        self._sem = sem
        self._scheduler = scheduler
        self._started = 0.0
        self._acquired = False

    def __enter__(self) -> None:
        self._started = time.perf_counter()
        if self._sem is not None:
            self._sem.acquire()
        self._acquired = True
        if self._scheduler is not None:
            self._scheduler._record_phase_acquire("prepare", time.perf_counter() - self._started, active_key="builds")
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._acquired and self._sem is not None:
            self._sem.release()
        if self._acquired and self._scheduler is not None:
            self._scheduler._record_phase_release(active_key="builds", hold_s=time.perf_counter() - self._started, phase_name="prepare")
        return None


class _AsyncSemaphoreContext:
    def __init__(
        self,
        *,
        sem: asyncio.Semaphore | None,
        wait_phase: str | None,
        active_key: str | None,
        phase_name: str | None,
        scheduler: ResourceScheduler,
        on_admission_acquire=None,  # type: ignore[no-untyped-def]
        on_admission_release=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self._sem = sem
        self._wait_phase = wait_phase
        self._active_key = active_key
        self._phase_name = phase_name
        self._scheduler = scheduler
        self._on_admission_acquire = on_admission_acquire
        self._on_admission_release = on_admission_release
        self._acquired = False
        self._started = 0.0

    async def __aenter__(self) -> None:
        self._started = time.perf_counter()
        if self._sem is not None:
            await self._sem.acquire()
        self._acquired = True
        wait_s = time.perf_counter() - self._started
        if self._on_admission_acquire is not None:
            self._on_admission_acquire(wait_s)
        else:
            self._scheduler._record_phase_acquire(self._wait_phase or "", wait_s, active_key=self._active_key)
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._acquired and self._sem is not None:
            self._sem.release()
        hold_s = time.perf_counter() - self._started
        if self._acquired:
            if self._on_admission_release is not None:
                self._on_admission_release(hold_s)
            else:
                self._scheduler._record_phase_release(
                    active_key=self._active_key,
                    hold_s=hold_s,
                    phase_name=self._phase_name,
                )
        return None


def _normalize_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, int(value))


def _normalize_required_limit(value: int | None) -> int:
    if value is None:
        return 1
    return max(1, int(value))
