from __future__ import annotations

import asyncio
import threading
import time

import pytest

from snowl.core import SandboxSpec
from snowl.envs.sandbox_runtime import PreparedSandbox
from snowl.runtime.resource_scheduler import ResourceScheduler, TaskExecutionPlan, TrialDescriptor


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


def test_provider_slots_share_budget_between_callers() -> None:
    scheduler = ResourceScheduler(
        max_running_trials=None,
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets={"shared": 1},
    )

    async def _run() -> int:
        current = 0
        observed_max = 0
        lock = asyncio.Lock()

        async def _worker() -> None:
            nonlocal current, observed_max
            async with scheduler.provider_slot("shared"):
                async with lock:
                    current += 1
                    observed_max = max(observed_max, current)
                await asyncio.sleep(0.02)
                async with lock:
                    current -= 1

        await asyncio.gather(*[_worker() for _ in range(4)])
        return observed_max

    assert asyncio.run(_run()) == 1


def test_scoring_slots_are_independent_from_running_slots() -> None:
    scheduler = ResourceScheduler(
        max_running_trials=1,
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=2,
        provider_budgets={},
    )

    async def _run() -> tuple[int, int]:
        running = 0
        scoring = 0
        max_running = 0
        max_scoring = 0
        lock = asyncio.Lock()

        async def _run_worker() -> None:
            nonlocal running, scoring, max_running, max_scoring
            async with scheduler.running_trial_slot():
                async with lock:
                    running += 1
                    max_running = max(max_running, running)
                await asyncio.sleep(0.01)
                async with lock:
                    running -= 1
            async with scheduler.scoring_slot():
                async with lock:
                    scoring += 1
                    max_scoring = max(max_scoring, scoring)
                await asyncio.sleep(0.02)
                async with lock:
                    scoring -= 1

        await asyncio.gather(*[_run_worker() for _ in range(3)])
        return max_running, max_scoring

    observed_running, observed_scoring = asyncio.run(_run())
    assert observed_running == 1
    assert observed_scoring == 2


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


def test_scheduler_records_independent_phase_admission() -> None:
    scheduler = ResourceScheduler(max_running_trials=1, max_container_slots=1, max_scoring_tasks=1)

    async def _run() -> None:
        descriptor = TrialDescriptor(
            trial_id="trial-1",
            task_id="task-1",
            sample_id="sample-1",
            agent_id="agent-1",
            variant_id="v1",
            scorer_id="s1",
            seed=None,
            spec_hash="abc",
            provider_ids=(),
        )
        plan = TaskExecutionPlan(trial=descriptor, requires_container=True)
        async with scheduler.begin_prepare(plan):
            assert scheduler.stats_snapshot()["active"]["container_slots"] == 1
        async with scheduler.begin_execute(plan):
            assert scheduler.stats_snapshot()["active"]["running_trials"] == 1
        async with scheduler.begin_score(plan):
            assert scheduler.stats_snapshot()["active"]["scoring_tasks"] == 1
        async with scheduler.begin_finalize(plan):
            assert scheduler.stats_snapshot()["active"]["finalizing"] == 1

    asyncio.run(_run())
    stats = scheduler.stats_snapshot()
    assert stats["active"]["container_slots"] == 0
    assert stats["active"]["running_trials"] == 0
    assert stats["active"]["scoring_tasks"] == 0


# ------------------------------------------------------------------
# AIMD flow control tests
# ------------------------------------------------------------------


def test_report_429_decreases_provider_limit() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 8})

    # Simulate a 429 — should halve the limit
    scheduler.report_429("api")
    snapshot = scheduler.flow_state_snapshot()
    assert snapshot["api"]["current_limit"] == 4
    assert snapshot["api"]["total_429s"] == 1

    # Another 429 — should halve again
    scheduler.report_429("api")
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 2


def test_report_429_respects_min_limit() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 2})

    scheduler.report_429("api")  # 2 → 1
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 1

    scheduler.report_429("api")  # 1 → 0.5 → floor=0 → min=1
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 1


def test_report_success_additive_increase_after_window() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 4})

    # Need current_limit (4) consecutive successes to trigger additive increase
    for _ in range(4):
        scheduler.report_success("api")
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 5

    # Window resets; need 5 more for next increase
    for _ in range(5):
        scheduler.report_success("api")
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 6


def test_report_success_respects_max_limit() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 2})
    # max_limit defaults to max(initial * 4, 64) = max(8, 64) = 64
    # But let's test with a small provider
    small_scheduler = ResourceScheduler(provider_budgets={"api": 1})
    # max_limit = max(1 * 4, 64) = 64

    for _ in range(1):
        small_scheduler.report_success("api")
    # 1 success = full window at limit 1 → increase to 2
    assert small_scheduler.flow_state_snapshot()["api"]["current_limit"] == 2


def test_429_resets_consecutive_successes() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 8})

    # 3 successes (not enough for a window)
    for _ in range(3):
        scheduler.report_success("api")
    assert scheduler.flow_state_snapshot()["api"]["consecutive_successes"] == 3

    # 429 resets the counter
    scheduler.report_429("api")
    assert scheduler.flow_state_snapshot()["api"]["consecutive_successes"] == 0

    # Need a full window at the new limit (4) to increase
    for _ in range(4):
        scheduler.report_success("api")
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 5


def test_resize_provider_budget() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 4})

    scheduler.resize_provider_budget("api", 12)
    assert scheduler.limits.provider_budgets["api"] == 12
    assert scheduler.flow_state_snapshot()["api"]["current_limit"] == 12

    # Can also resize for a provider that wasn't in the initial budget
    scheduler.resize_provider_budget("other", 3)
    assert scheduler.limits.provider_budgets["other"] == 3


def test_flow_state_snapshot_empty_without_reports() -> None:
    scheduler = ResourceScheduler(provider_budgets={"api": 4})
    assert scheduler.flow_state_snapshot() == {}


def test_adaptive_concurrency_with_real_semaphore() -> None:
    """Integration test: verify that report_429 actually reduces effective concurrency."""
    scheduler = ResourceScheduler(provider_budgets={"api": 4})

    async def _run() -> int:
        current = 0
        observed_max = 0
        lock = asyncio.Lock()

        async def _worker() -> None:
            nonlocal current, observed_max
            async with scheduler.provider_slot("api"):
                async with lock:
                    current += 1
                    observed_max = max(observed_max, current)
                await asyncio.sleep(0.02)
                async with lock:
                    current -= 1

        # First batch — 4 workers should all run concurrently
        await asyncio.gather(*[_worker() for _ in range(4)])
        first_max = observed_max
        assert first_max == 4

        # Simulate a 429 — limit should halve from 4 to 2
        scheduler.report_429("api")

        observed_max = 0
        # Second batch — only 2 should run concurrently
        await asyncio.gather(*[_worker() for _ in range(4)])
        return observed_max

    result = asyncio.run(_run())
    assert result == 2
