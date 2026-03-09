"""Unified resource scheduler for eval/runtime quotas."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from snowl.envs.sandbox_runtime import PreparedSandbox, SandboxRuntime


@dataclass(frozen=True)
class ResourceLimits:
    max_trials: int | None
    max_sandboxes: int | None
    max_builds: int | None
    max_model_calls: int | None


class ResourceScheduler:
    def __init__(
        self,
        *,
        max_trials: int | None,
        max_sandboxes: int | None,
        max_builds: int | None,
        max_model_calls: int | None,
    ) -> None:
        self._limits = ResourceLimits(
            max_trials=_normalize_limit(max_trials),
            max_sandboxes=_normalize_limit(max_sandboxes),
            max_builds=_normalize_limit(max_builds),
            max_model_calls=_normalize_limit(max_model_calls),
        )
        self._trial_sem: asyncio.Semaphore | None = None
        self._sandbox_sem: asyncio.Semaphore | None = None
        self._model_call_sem: asyncio.Semaphore | None = None
        self._build_sem: threading.BoundedSemaphore | None = (
            threading.BoundedSemaphore(self._limits.max_builds)
            if self._limits.max_builds is not None
            else None
        )

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    def controls(self) -> dict[str, int | None]:
        return {
            "max_trials": self._limits.max_trials,
            "max_sandboxes": self._limits.max_sandboxes,
            "max_builds": self._limits.max_builds,
            "max_model_calls": self._limits.max_model_calls,
        }

    @asynccontextmanager
    async def trial_slot(self) -> AsyncIterator[None]:
        sem = self._get_trial_sem()
        if sem is None:
            yield None
            return
        await sem.acquire()
        try:
            yield None
        finally:
            sem.release()

    @asynccontextmanager
    async def model_call_slot(self) -> AsyncIterator[None]:
        sem = self._get_model_call_sem()
        if sem is None:
            yield None
            return
        await sem.acquire()
        try:
            yield None
        finally:
            sem.release()

    def build_slot(self) -> _BuildSemaphoreContext:
        return _BuildSemaphoreContext(self._build_sem)

    async def acquire_sandbox_slot(self) -> None:
        sem = self._get_sandbox_sem()
        if sem is None:
            return
        await sem.acquire()

    def release_sandbox_slot(self) -> None:
        sem = self._get_sandbox_sem()
        if sem is None:
            return
        sem.release()

    def wrap_sandbox_runtime(self, inner: SandboxRuntime) -> SandboxRuntime:
        return _ScheduledSandboxRuntime(inner=inner, scheduler=self)

    def _get_trial_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_trials is None:
            return None
        if self._trial_sem is None:
            self._trial_sem = asyncio.Semaphore(self._limits.max_trials)
        return self._trial_sem

    def _get_sandbox_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_sandboxes is None:
            return None
        if self._sandbox_sem is None:
            self._sandbox_sem = asyncio.Semaphore(self._limits.max_sandboxes)
        return self._sandbox_sem

    def _get_model_call_sem(self) -> asyncio.Semaphore | None:
        if self._limits.max_model_calls is None:
            return None
        if self._model_call_sem is None:
            self._model_call_sem = asyncio.Semaphore(self._limits.max_model_calls)
        return self._model_call_sem


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


def _normalize_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, int(value))
