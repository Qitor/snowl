"""Tests for BenchmarkConcurrencyProfile and RuntimePolicy integration."""

from __future__ import annotations

import pytest

from snowl.benchmarks.base import BenchmarkConcurrencyProfile, BenchmarkInfo
from snowl.core import EnvSpec, Task
from snowl.runtime.policy import RuntimePolicy, _get_benchmark_profile_from_registry


def _task_with_benchmark(benchmark_name: str) -> Task:
    return Task(
        task_id="t1",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([]),
        metadata={"benchmark": benchmark_name},
    )


# ---------------------------------------------------------------------------
# BenchmarkConcurrencyProfile
# ---------------------------------------------------------------------------


def test_profile_defaults():
    profile = BenchmarkConcurrencyProfile(name="test")
    assert profile.api_call_amplification == 1.0
    assert profile.recommended_max_running is None
    assert profile.scorer_uses_provider is False
    assert profile.scorer_provider_id is None
    assert profile.recommended_scoring_tasks is None


def test_profile_custom_values():
    profile = BenchmarkConcurrencyProfile(
        name="toolemu",
        api_call_amplification=30.0,
        recommended_max_running=3,
        scorer_uses_provider=True,
        scorer_provider_id="openai",
    )
    assert profile.api_call_amplification == 30.0
    assert profile.recommended_max_running == 3
    assert profile.scorer_uses_provider is True


# ---------------------------------------------------------------------------
# BenchmarkInfo with profile
# ---------------------------------------------------------------------------


def test_benchmark_info_with_profile():
    info = BenchmarkInfo(
        name="test_bench",
        description="Test",
        concurrency_profile=BenchmarkConcurrencyProfile(name="test_bench", recommended_max_running=4),
    )
    assert info.concurrency_profile is not None
    assert info.concurrency_profile.recommended_max_running == 4


def test_benchmark_info_without_profile():
    info = BenchmarkInfo(name="test_bench", description="Test")
    assert info.concurrency_profile is None


# ---------------------------------------------------------------------------
# _get_benchmark_profile_from_registry
# ---------------------------------------------------------------------------


def test_get_benchmark_profile_returns_toolemu_profile():
    profile = _get_benchmark_profile_from_registry("toolemu")
    assert profile is not None
    assert profile.name == "toolemu"
    assert profile.recommended_max_running == 3
    assert profile.scorer_uses_provider is True


def test_get_benchmark_profile_returns_agentdojo_profile():
    profile = _get_benchmark_profile_from_registry("agentdojo")
    assert profile is not None
    assert profile.name == "agentdojo"
    assert profile.recommended_max_running == 6


def test_get_benchmark_profile_returns_none_for_unknown_benchmark():
    profile = _get_benchmark_profile_from_registry("nonexistent_bench")
    assert profile is None


# ---------------------------------------------------------------------------
# RuntimePolicy integration
# ---------------------------------------------------------------------------


def test_runtime_policy_applies_profile_max_running():
    """When no explicit override, profile recommended_max_running is applied."""
    task = _task_with_benchmark("toolemu")
    profile = _get_benchmark_profile_from_registry("toolemu")
    policy = RuntimePolicy()
    resolution = policy.resolve(
        tasks=[task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=None,
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets=None,
        concurrency_profile=profile,
    )
    # ToolEmu profile recommends max_running=3, which should cap the default
    assert resolution.max_running_trials <= 3


def test_runtime_policy_explicit_override_wins():
    """When an explicit --max-running-trials is provided, it takes precedence."""
    task = _task_with_benchmark("toolemu")
    profile = _get_benchmark_profile_from_registry("toolemu")
    policy = RuntimePolicy()
    resolution = policy.resolve(
        tasks=[task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=10,  # explicit override
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets=None,
        concurrency_profile=profile,
    )
    assert resolution.max_running_trials == 10


def test_runtime_policy_adds_scorer_provider_budget():
    """When profile has scorer_uses_provider, scorer provider is added to budget."""
    task = _task_with_benchmark("toolemu")
    profile = _get_benchmark_profile_from_registry("toolemu")
    policy = RuntimePolicy()
    resolution = policy.resolve(
        tasks=[task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=None,
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets=None,
        concurrency_profile=profile,
    )
    assert "openai" in resolution.provider_budgets


def test_runtime_policy_no_profile_no_change():
    """Benchmarks without profiles get default behavior."""
    task = _task_with_benchmark("strongreject")
    policy = RuntimePolicy()
    resolution = policy.resolve(
        tasks=[task],
        project_config=None,
        interaction_controller=None,
        max_running_trials=None,
        max_container_slots=None,
        max_builds=None,
        max_scoring_tasks=None,
        provider_budgets=None,
        # No concurrency_profile — should use defaults
    )
    # Default: min(8, cpu_count) — should NOT be capped by any profile
    assert resolution.max_running_trials >= 1
