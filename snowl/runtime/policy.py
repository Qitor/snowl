"""Runtime budget policy and heuristics for eval runs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from snowl.benchmarks.base import BenchmarkConcurrencyProfile
from snowl.core import Task
from snowl.project_config import ProjectConfig


@dataclass(frozen=True)
class RuntimeBudgetResolution:
    max_running_trials: int
    max_container_slots: int | None
    max_builds: int
    max_scoring_tasks: int
    provider_budgets: dict[str, int]
    auto_container_slots: int | None
    docker_like: bool

    def to_scheduler_kwargs(self) -> dict[str, Any]:
        return {
            "max_running_trials": self.max_running_trials,
            "max_container_slots": self.max_container_slots,
            "max_builds": self.max_builds,
            "max_scoring_tasks": self.max_scoring_tasks,
            "provider_budgets": dict(self.provider_budgets),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_running_trials": self.max_running_trials,
            "max_container_slots": self.max_container_slots,
            "max_builds": self.max_builds,
            "max_scoring_tasks": self.max_scoring_tasks,
            "provider_budgets": dict(self.provider_budgets),
            "auto_container_slots": self.auto_container_slots,
            "docker_like": self.docker_like,
        }


def available_memory_gb() -> float | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return float(page_size * avail_pages) / (1024.0**3)
    except Exception:
        return None


def _get_runtime_hints(benchmark: str) -> dict[str, Any]:
    """Look up runtime_hints from benchmark registry."""
    try:
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        for entry in registry.list():
            if entry.info.name == benchmark:
                return entry.info.runtime_hints
    except Exception:
        pass
    return {}


def _get_container_slots_profile(benchmark: str) -> dict[str, Any] | None:
    """Look up container_slots_profile from benchmark registry runtime_hints."""
    hints = _get_runtime_hints(benchmark)
    profile = hints.get("container_slots_profile")
    return profile if isinstance(profile, dict) else None


def auto_container_slots(*, benchmark: str, cpu_count: int | None = None, mem_gb: float | None = None) -> int:
    cpu = max(1, int(cpu_count or os.cpu_count() or 1))
    memory = mem_gb if mem_gb is not None else available_memory_gb()
    benchmark_key = str(benchmark or "").strip().lower()

    # No containers for non-container benchmarks
    if benchmark_key in {"", "custom", "strongreject", "toolemu", "agentsafetybench"}:
        return 0

    # Try registry-driven profile
    profile = _get_container_slots_profile(benchmark_key)
    if profile is not None:
        max_slots = profile.get("max_slots", 2)
        cpu_divisor = profile.get("cpu_divisor", 2)
        mem_per_slot = profile.get("mem_per_slot_gb", 4)
        by_cpu = max(1, min(max_slots, cpu // cpu_divisor or 1))
        if memory is None:
            return by_cpu
        return max(1, min(by_cpu, int(memory // mem_per_slot) or 1))

    # Default heuristic
    return max(1, min(2, cpu // 2 or 1))


def benchmark_name_for_task(task: Task) -> str:
    metadata = getattr(task, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return "custom"
    value = str(metadata.get("benchmark") or metadata.get("benchmark_name") or "").strip().lower()
    return value or "custom"


def _get_benchmark_profile(tasks: list[Task]) -> BenchmarkConcurrencyProfile | None:
    """Look up the concurrency profile from the benchmark registry for the given tasks."""
    if not tasks:
        return None
    benchmark_names = sorted({benchmark_name_for_task(t) for t in tasks})
    if len(benchmark_names) != 1:
        return None  # Mixed benchmarks; no single profile applies
    benchmark_name = benchmark_names[0]
    try:
        from snowl.benchmarks.registry import get_default_benchmark_registry
        registry = get_default_benchmark_registry()
        for entry in registry.list():
            if entry.info.name == benchmark_name and entry.info.concurrency_profile is not None:
                return entry.info.concurrency_profile
    except Exception:
        pass
    return None


def is_docker_like_task(task: Task) -> bool:
    try:
        env_type = str(getattr(task.env_spec, "env_type", "") or "").lower()
    except Exception:
        env_type = ""
    if env_type in {"terminal", "gui", "docker"}:
        return True
    try:
        sandbox_spec = getattr(task.env_spec, "sandbox_spec", None)
        if sandbox_spec is not None:
            provider = str(getattr(sandbox_spec, "provider", "") or "").lower()
            if provider in {"docker", "podman"}:
                return True
    except Exception:
        pass
    # Check registry hint
    bench_name = benchmark_name_for_task(task)
    if bench_name and bench_name != "custom":
        hints = _get_runtime_hints(bench_name)
        if hints.get("is_docker_like") is True:
            return True
    return False


class RuntimePolicy:
    """Resolve eval runtime controls from config, overrides, and heuristics.

    This policy owns budget defaults such as docker-like serial execution. It
    does not create schedulers, dispatch trials, or interpret retry behavior.
    """

    def resolve(
        self,
        *,
        tasks: list[Task],
        project_config: ProjectConfig | None,
        interaction_controller: Any | None,
        max_running_trials: int | None,
        max_container_slots: int | None,
        max_builds: int | None,
        max_scoring_tasks: int | None,
        provider_budgets: dict[str, int] | None,
    ) -> RuntimeBudgetResolution:
        runtime_cfg = project_config.runtime if project_config is not None else None
        explicit_running = max_running_trials is not None
        benchmark_names = sorted({benchmark_name_for_task(task) for task in tasks})
        benchmark_hint = benchmark_names[0] if len(benchmark_names) == 1 else "mixed"

        if max_running_trials is None:
            max_running_trials = runtime_cfg.max_running_trials if runtime_cfg is not None else None
        if max_builds is None:
            max_builds = runtime_cfg.max_builds if runtime_cfg is not None else None
        if max_scoring_tasks is None:
            max_scoring_tasks = runtime_cfg.max_scoring_tasks if runtime_cfg is not None else None
        if provider_budgets is None:
            provider_budgets = dict(runtime_cfg.provider_budgets) if runtime_cfg is not None else {}

        auto_container = False
        if max_container_slots is None:
            raw = runtime_cfg.max_container_slots if runtime_cfg is not None else "auto"
            if isinstance(raw, str) and raw.strip().lower() == "auto":
                auto_container = True
                max_container_slots = auto_container_slots(benchmark=benchmark_hint)
            elif raw is None:
                auto_container = True
                max_container_slots = auto_container_slots(benchmark=benchmark_hint)
            else:
                max_container_slots = int(raw)

        if max_running_trials is None:
            max_running_trials = min(8, max(1, int(os.cpu_count() or 4)))
        if max_builds is None:
            max_builds = 2
        if max_scoring_tasks is None:
            max_scoring_tasks = max_running_trials

        if interaction_controller is not None:
            max_running_trials = 1
        docker_like = any(is_docker_like_task(t) for t in tasks)
        if docker_like and not explicit_running:
            max_running_trials = 1

        # Apply benchmark concurrency profile if available and no explicit overrides
        profile = _get_benchmark_profile(tasks)
        if profile is not None:
            if profile.recommended_max_running is not None and not explicit_running and not docker_like:
                max_running_trials = min(max_running_trials, profile.recommended_max_running)
            if profile.recommended_scoring_tasks is not None and max_scoring_tasks is None:
                if runtime_cfg is None or runtime_cfg.max_scoring_tasks is None:
                    max_scoring_tasks = min(max_scoring_tasks, profile.recommended_scoring_tasks)

        provider_budget_map = dict(provider_budgets or {})
        if project_config is not None and project_config.provider.id not in provider_budget_map:
            provider_budget_map[project_config.provider.id] = max(max_running_trials, max_scoring_tasks)
        # Add per-endpoint budgets for models with distinct provider_ids
        if project_config is not None:
            for model_entry in project_config.agent_matrix:
                pid = model_entry.config.provider_id
                if pid not in provider_budget_map:
                    provider_budget_map[pid] = max(max_running_trials, max_scoring_tasks)
        if not provider_budget_map:
            provider_budget_map["default"] = max(max_running_trials, max_scoring_tasks)

        # Add scorer provider budget if the benchmark profile requires it
        if profile is not None and profile.scorer_uses_provider and profile.scorer_provider_id:
            scorer_provider = profile.scorer_provider_id
            if scorer_provider not in provider_budget_map:
                provider_budget_map[scorer_provider] = max(max_running_trials, 1)

        return RuntimeBudgetResolution(
            max_running_trials=max_running_trials,
            max_container_slots=max_container_slots,
            max_builds=max_builds,
            max_scoring_tasks=max_scoring_tasks,
            provider_budgets=provider_budget_map,
            auto_container_slots=max_container_slots if auto_container else None,
            docker_like=docker_like,
        )
