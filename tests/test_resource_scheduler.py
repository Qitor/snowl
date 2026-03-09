from __future__ import annotations

import asyncio
import threading
import time

import pytest

from snowl.core import SandboxSpec
from snowl.envs.sandbox_runtime import PreparedSandbox
from snowl.runtime.resource_scheduler import ResourceScheduler


def test_trial_slots_enforce_quota() -> None:
    scheduler = ResourceScheduler(
        max_trials=2,
        max_sandboxes=None,
        max_builds=None,
        max_model_calls=None,
    )

    async def _run() -> int:
        current = 0
        observed_max = 0
        lock = asyncio.Lock()

        async def _worker() -> None:
            nonlocal current, observed_max
            async with scheduler.trial_slot():
                async with lock:
                    current += 1
                    observed_max = max(observed_max, current)
                await asyncio.sleep(0.03)
                async with lock:
                    current -= 1

        await asyncio.gather(*[_worker() for _ in range(6)])
        return observed_max

    assert asyncio.run(_run()) <= 2


def test_model_call_slots_enforce_quota() -> None:
    scheduler = ResourceScheduler(
        max_trials=None,
        max_sandboxes=None,
        max_builds=None,
        max_model_calls=1,
    )

    async def _run() -> int:
        current = 0
        observed_max = 0
        lock = asyncio.Lock()

        async def _worker() -> None:
            nonlocal current, observed_max
            async with scheduler.model_call_slot():
                async with lock:
                    current += 1
                    observed_max = max(observed_max, current)
                await asyncio.sleep(0.02)
                async with lock:
                    current -= 1

        await asyncio.gather(*[_worker() for _ in range(4)])
        return observed_max

    assert asyncio.run(_run()) == 1


def test_build_slots_enforce_quota() -> None:
    scheduler = ResourceScheduler(
        max_trials=None,
        max_sandboxes=None,
        max_builds=1,
        max_model_calls=None,
    )

    counters = {"current": 0, "max": 0}
    lock = threading.Lock()

    def _worker() -> None:
        with scheduler.build_slot():
            with lock:
                counters["current"] += 1
                counters["max"] = max(counters["max"], counters["current"])
            time.sleep(0.03)
            with lock:
                counters["current"] -= 1

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert counters["max"] == 1


def test_sandbox_slots_release_on_teardown_and_prepare_failure() -> None:
    scheduler = ResourceScheduler(
        max_trials=None,
        max_sandboxes=1,
        max_builds=None,
        max_model_calls=None,
    )
    spec = SandboxSpec(provider="docker", image="python:3.12")

    class _Runtime:
        async def prepare(self, _spec: SandboxSpec) -> PreparedSandbox:
            return PreparedSandbox(
                sandbox_id="sb1",
                spec_hash="h1",
                provider="docker",
                prepared_at_ms=1,
                diagnostics={},
            )

        async def run(self, prepared: PreparedSandbox, operation):  # type: ignore[no-untyped-def]
            _ = prepared
            return await operation()

        async def teardown(self, prepared: PreparedSandbox) -> dict[str, object]:
            return {"sandbox_id": prepared.sandbox_id}

    class _FailingRuntime(_Runtime):
        async def prepare(self, _spec: SandboxSpec) -> PreparedSandbox:
            raise RuntimeError("prepare failed")

    wrapped = scheduler.wrap_sandbox_runtime(_Runtime())
    wrapped_fail = scheduler.wrap_sandbox_runtime(_FailingRuntime())

    async def _run() -> None:
        first = await wrapped.prepare(spec)
        second_done = asyncio.Event()

        async def _second_prepare() -> None:
            second = await wrapped.prepare(spec)
            await wrapped.teardown(second)
            second_done.set()

        second_task = asyncio.create_task(_second_prepare())
        await asyncio.sleep(0.03)
        assert not second_done.is_set()
        await wrapped.teardown(first)
        await asyncio.wait_for(second_task, timeout=1.0)

        with pytest.raises(RuntimeError, match="prepare failed"):
            await wrapped_fail.prepare(spec)
        extra = await wrapped.prepare(spec)
        await wrapped.teardown(extra)

    asyncio.run(_run())
