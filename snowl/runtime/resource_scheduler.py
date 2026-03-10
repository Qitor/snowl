"""Provider-aware resource scheduler for eval/runtime quotas."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from snowl.envs.sandbox_runtime import PreparedSandbox, SandboxRuntime


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
            "running_trials": 0,
            "scoring_tasks": 0,
            "container_slots": 0,
        }
        self._provider_inflight: dict[str, int] = {}
        self._queue_wait_totals: dict[str, float] = {
            "running": 0.0,
            "scoring": 0.0,
            "container": 0.0,
        }
        self._queue_wait_counts: dict[str, int] = {
            "running": 0,
            "scoring": 0,
            "container": 0,
        }
        self._provider_queue_wait_totals: dict[str, float] = {}
        self._provider_queue_wait_counts: dict[str, int] = {}

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
            # Legacy aliases kept for tests / monitor compatibility while the
            # rest of the stack migrates to the new names.
            "max_trials": self._limits.max_running_trials,
            "max_sandboxes": self._limits.max_container_slots,
            "max_model_calls": legacy_model_calls,
        }

    def stats_snapshot(self) -> dict[str, Any]:
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
            return {
                "phase_counts": {
                    "running": self._active["running_trials"],
                    "scoring": self._active["scoring_tasks"],
                    "preparing": self._active["container_slots"],
                },
                "queue_wait_ms": {
                    **queue_wait_ms,
                    "providers": provider_wait_ms,
                },
                "provider_utilization": provider_utilization,
                "provider_inflight": dict(self._provider_inflight),
                "active_running_trials": self._active["running_trials"],
                "active_scoring_tasks": self._active["scoring_tasks"],
                "active_container_slots": self._active["container_slots"],
            }

    @asynccontextmanager
    async def running_trial_slot(self) -> AsyncIterator[None]:
        sem = self._get_running_sem()
        async with _AsyncSemaphoreContext(
            sem=sem,
            on_acquire=lambda wait: self._record_phase_acquire("running", wait, active_key="running_trials"),
            on_release=lambda hold: self._record_phase_release(active_key="running_trials", _hold=hold),
        ):
            yield None

    @asynccontextmanager
    async def scoring_slot(self) -> AsyncIterator[None]:
        sem = self._get_scoring_sem()
        async with _AsyncSemaphoreContext(
            sem=sem,
            on_acquire=lambda wait: self._record_phase_acquire("scoring", wait, active_key="scoring_tasks"),
            on_release=lambda hold: self._record_phase_release(active_key="scoring_tasks", _hold=hold),
        ):
            yield None

    @asynccontextmanager
    async def provider_slot(self, provider_id: str | None) -> AsyncIterator[None]:
        key = str(provider_id or "default").strip() or "default"
        sem = self._get_provider_sem(key)
        async with _AsyncSemaphoreContext(
            sem=sem,
            on_acquire=lambda wait: self._record_provider_acquire(key, wait),
            on_release=lambda hold: self._record_provider_release(key, _hold=hold),
        ):
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
        return _BuildSemaphoreContext(self._build_sem)

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
        self._record_phase_release(active_key="container_slots", _hold=0.0)

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

    def _record_phase_acquire(self, phase: str, wait_s: float, *, active_key: str) -> None:
        with self._stats_lock:
            self._queue_wait_totals[phase] = self._queue_wait_totals.get(phase, 0.0) + max(0.0, float(wait_s))
            self._queue_wait_counts[phase] = self._queue_wait_counts.get(phase, 0) + 1
            self._active[active_key] = self._active.get(active_key, 0) + 1

    def _record_phase_release(self, *, active_key: str, _hold: float) -> None:
        with self._stats_lock:
            self._active[active_key] = max(0, self._active.get(active_key, 0) - 1)

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
    def __init__(self, sem: threading.BoundedSemaphore | None) -> None:
        self._sem = sem

    def __enter__(self) -> None:
        if self._sem is not None:
            self._sem.acquire()
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sem is not None:
            self._sem.release()
        return None


class _AsyncSemaphoreContext:
    def __init__(self, *, sem: asyncio.Semaphore | None, on_acquire, on_release) -> None:  # type: ignore[no-untyped-def]
        self._sem = sem
        self._on_acquire = on_acquire
        self._on_release = on_release
        self._acquired = False
        self._started = 0.0

    async def __aenter__(self) -> None:
        self._started = time.perf_counter()
        if self._sem is not None:
            await self._sem.acquire()
        self._acquired = True
        self._on_acquire(time.perf_counter() - self._started)
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._acquired and self._sem is not None:
            self._sem.release()
        if self._acquired:
            self._on_release(time.perf_counter() - self._started)
        return None


def _normalize_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, int(value))


def _normalize_required_limit(value: int | None) -> int:
    if value is None:
        return 1
    return max(1, int(value))
