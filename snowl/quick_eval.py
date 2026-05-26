"""Quick evaluation API — evaluate any agent against any benchmark in one call.

Framework role:
- Provides ``quick_eval()`` and ``quick_eval_sync()`` as the simplest entry points
  for running Snowl evaluations without understanding internal APIs.
- Wraps CustomAdapter, TrialRequest, and execute_trial into a single function call.

Runtime/usage wiring:
- Imported via ``from snowl import quick_eval``.
- Designed for notebooks, scripts, and onboarding — not for production eval pipelines
  (use ``snowl eval`` or ``execute_trial()`` directly for full control).

Change guardrails:
- The ``quick_eval()`` signature is a public API. Changes must be backwards-compatible.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from snowl.adapters.custom import CustomAdapter, _CustomAgent
from snowl.core import EnvSpec, Task
from snowl.core.agent import Agent
from snowl.core.scorer import Scorer
from snowl.runtime.engine import TrialRequest, execute_trial


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuickEvalResult:
    """Human-friendly evaluation result from ``quick_eval()``."""

    status: str  # "success" | "incorrect" | "error" | "mixed"
    pass_rate: float  # 0.0 - 1.0
    scores: dict[str, float]  # {"includes": 1.0, "judge": 0.8}
    total_tokens: int
    duration_ms: int
    sample_count: int
    output_dir: str | None = None

    def __str__(self) -> str:
        lines = [
            f"QuickEvalResult: {self.pass_rate:.0%} pass rate ({self.sample_count} samples)",
            f"  Status: {self.status}",
            f"  Scores: {self.scores}",
            f"  Tokens: {self.total_tokens}  Duration: {self.duration_ms}ms",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scorer name → factory mapping
# ---------------------------------------------------------------------------

_SCORER_FACTORIES: dict[str, Callable[..., Scorer]] = {}


def _init_scorer_factories() -> None:
    """Lazily populate scorer factory map (avoid heavy imports at module level)."""
    if _SCORER_FACTORIES:
        return
    from snowl.scorer import includes, match, pattern, model_as_judge_json
    from snowl.scorer.choice import choice_answer
    from snowl.scorer.agent import answer_match, function_call_match
    _SCORER_FACTORIES.update({
        "includes": includes,
        "match": match,
        "pattern": pattern,
        "model_as_judge_json": model_as_judge_json,
        "choice_answer": choice_answer,
        "answer_match": answer_match,
        "function_call_match": function_call_match,
    })


def _resolve_scorer(scorer: Scorer | str | None) -> Any:
    """Normalize scorer input to a Scorer instance."""
    if scorer is None:
        return None
    if isinstance(scorer, str):
        _init_scorer_factories()
        factory = _SCORER_FACTORIES.get(scorer)
        if factory is None:
            raise ValueError(
                f"Unknown scorer name '{scorer}'. "
                f"Available: {sorted(_SCORER_FACTORIES.keys())}. "
                f"Or pass a Scorer instance directly."
            )
        return factory()
    # Assume it's a Scorer instance (duck-typing — Scorer is a non-runtime Protocol)
    if hasattr(scorer, "scorer_id") and callable(getattr(scorer, "score", None)):
        return scorer
    raise TypeError(f"scorer must be a Scorer instance or string name, got {type(scorer).__name__}")


# ---------------------------------------------------------------------------
# Agent normalization
# ---------------------------------------------------------------------------

def _resolve_agent(agent: Any) -> Agent:
    """Normalize agent input to an Agent instance."""
    if hasattr(agent, "agent_id") and hasattr(agent, "run"):
        # Already an Agent — use directly
        return agent
    if callable(agent):
        # Bare callable — wrap via CustomAdapter
        return CustomAdapter().wrap(agent)
    raise TypeError(
        f"agent must be a callable or an Agent instance with agent_id + run(), "
        f"got {type(agent).__name__}"
    )


# ---------------------------------------------------------------------------
# Sample collection from benchmark
# ---------------------------------------------------------------------------

def _samples_from_benchmark(
    benchmark: str,
    limit: int | None = None,
) -> tuple[Task, list[dict[str, Any]]]:
    """Load samples from a named benchmark in the registry.

    Returns:
        (task, samples) — the task and extracted sample dicts.
    """
    from snowl.benchmarks.registry import get_default_benchmark_registry

    registry = get_default_benchmark_registry()
    try:
        adapter = registry.create(benchmark)
    except Exception as exc:
        available = sorted(e.info.name for e in registry.list())
        raise ValueError(
            f"Unknown benchmark '{benchmark}'. Available: {available}"
        ) from exc

    splits = adapter.list_splits()
    if not splits:
        raise ValueError(f"Benchmark '{benchmark}' has no splits.")
    split = splits[0]

    tasks = adapter.load_tasks(split=split, limit=limit or 10)
    if not tasks:
        raise ValueError(f"Benchmark '{benchmark}' returned no tasks for split '{split}'.")

    # Collect all samples from all tasks
    samples: list[dict[str, Any]] = []
    for task in tasks:
        for sample in task.iter_samples():
            samples.append(dict(sample) if not isinstance(sample, dict) else sample)

    if not samples:
        raise ValueError(f"Benchmark '{benchmark}' returned no samples.")

    # Return the first task (for env_spec and metadata) and all samples
    return tasks[0], samples


# ---------------------------------------------------------------------------
# quick_eval
# ---------------------------------------------------------------------------

async def quick_eval(
    *,
    agent: Any,
    benchmark: str | None = None,
    scorer: Scorer | str | None = None,
    samples: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    max_tokens: int = 256,
) -> QuickEvalResult:
    """Run a quick evaluation of an agent against samples or a benchmark.

    This is the simplest way to evaluate an agent with Snowl. No project.yml,
    no TrialRequest, no internal API knowledge required.

    Args:
        agent: A callable ``async def(messages, tools) -> result``, or an
            Agent instance with ``agent_id`` and ``run()``.
        benchmark: Name of a built-in benchmark (e.g. ``"strongreject"``).
            Mutually exclusive with ``samples``.
        scorer: A Scorer instance, a string name (``"includes"``, ``"match"``),
            or None for default.
        samples: Custom sample dicts ``[{"id": ..., "input": ..., "target": ...}]``.
            Mutually exclusive with ``benchmark``.
        limit: Max number of samples to evaluate.
        max_tokens: Token limit for agent responses.

    Returns:
        A ``QuickEvalResult`` with pass_rate, scores, cost, and duration.

    Raises:
        ValueError: If neither ``benchmark`` nor ``samples`` is provided,
            or if both are provided.
        TypeError: If ``agent`` is not callable or an Agent instance.

    Example::

        from snowl import quick_eval

        result = await quick_eval(
            agent=lambda msgs, tools: "I cannot help with that.",
            benchmark="strongreject",
            limit=10,
        )
        print(result)
    """
    # --- Validate inputs ---
    if benchmark and samples:
        raise ValueError("Provide either 'benchmark' or 'samples', not both.")
    if not benchmark and not samples:
        raise ValueError("Provide either 'benchmark' or 'samples'.")

    # --- Normalize agent ---
    resolved_agent = _resolve_agent(agent)

    # --- Normalize scorer ---
    resolved_scorer = _resolve_scorer(scorer)
    if resolved_scorer is None:
        resolved_scorer = _resolve_scorer("includes")

    # --- Get task + samples ---
    if benchmark:
        task, sample_list = _samples_from_benchmark(benchmark, limit=limit)
    else:
        task = Task(
            task_id="quick-eval",
            env_spec=EnvSpec(env_type="local"),
            sample_iter_factory=lambda: iter([]),
        )
        sample_list = samples or []

    if limit is not None:
        sample_list = sample_list[:limit]

    if not sample_list:
        raise ValueError("No samples to evaluate.")

    # --- Run trials ---
    start = time.monotonic()
    total_tokens = 0
    success_count = 0
    error_count = 0
    aggregate_scores: dict[str, list[float]] = {}

    for sample in sample_list:
        try:
            outcome = await execute_trial(TrialRequest(
                task=task,
                agent=resolved_agent,
                sample=sample,
                scorer=resolved_scorer,
            ))

            usage = outcome.task_result.usage
            if usage is not None:
                total_tokens += getattr(usage, "total_tokens", 0) or 0

            status_val = outcome.task_result.status.value
            if status_val == "success":
                success_count += 1

            for key, score in outcome.scores.items():
                aggregate_scores.setdefault(key, []).append(float(score.value))

        except Exception:
            error_count += 1

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # --- Aggregate ---
    total = len(sample_list)
    pass_rate = success_count / total if total > 0 else 0.0
    avg_scores = {
        key: sum(vals) / len(vals)
        for key, vals in aggregate_scores.items()
    }

    if error_count == total:
        status = "error"
    elif error_count > 0:
        status = "mixed"
    elif success_count == total:
        status = "success"
    else:
        status = "incorrect"

    return QuickEvalResult(
        status=status,
        pass_rate=pass_rate,
        scores=avg_scores,
        total_tokens=total_tokens,
        duration_ms=elapsed_ms,
        sample_count=total,
    )


def quick_eval_sync(**kwargs: Any) -> QuickEvalResult:
    """Synchronous wrapper for ``quick_eval()``.

    Identical to ``quick_eval()`` but can be called without ``await``.
    Useful for notebooks and simple scripts.

    Example::

        from snowl import quick_eval_sync

        result = quick_eval_sync(
            agent=lambda msgs, tools: "hello",
            samples=[{"id": "s1", "input": "Say hi", "target": "hello"}],
            scorer="includes",
        )
    """
    return asyncio.run(quick_eval(**kwargs))
