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
    duration_ms: int  # wall-clock total
    working_time_ms: int  # agent execution time (excludes scoring overhead)
    sample_count: int
    estimated_cost_usd: float | None = None
    score_per_dollar: float | None = None
    output_dir: str | None = None

    def __str__(self) -> str:
        lines = [
            f"QuickEvalResult: {self.pass_rate:.0%} pass rate ({self.sample_count} samples)",
            f"  Status: {self.status}",
            f"  Scores: {self.scores}",
            f"  Tokens: {self.total_tokens}  Duration: {self.duration_ms}ms  Working: {self.working_time_ms}ms",
        ]
        if self.estimated_cost_usd is not None:
            lines.append(f"  Cost: ${self.estimated_cost_usd:.4f}")
        if self.score_per_dollar is not None:
            lines.append(f"  Score/$: {self.score_per_dollar:.2f}")
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
    strip_canaries: bool = False,
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

    # --- Strip canary markers from inputs if requested ---
    if strip_canaries:
        from snowl.canary import strip_canary_from_sample
        sample_list = [strip_canary_from_sample(s) for s in sample_list]

    # --- Run trials ---
    start = time.monotonic()
    total_tokens = 0
    total_cost_usd = 0.0
    total_working_ms = 0
    success_count = 0
    error_count = 0
    aggregate_scores: dict[str, list[float]] = {}

    for sample in sample_list:
        try:
            trial_start = time.monotonic()
            outcome = await execute_trial(TrialRequest(
                task=task,
                agent=resolved_agent,
                sample=sample,
                scorer=resolved_scorer,
            ))
            trial_elapsed = int((time.monotonic() - trial_start) * 1000)

            # Agent execution time from TaskResult.Timing (excludes scoring)
            timing = outcome.task_result.timing
            if timing is not None:
                total_working_ms += getattr(timing, "duration_ms", 0) or 0
            else:
                total_working_ms += trial_elapsed

            usage = outcome.task_result.usage
            if usage is not None:
                total_tokens += getattr(usage, "total_tokens", 0) or 0
                cost = getattr(usage, "estimated_cost_usd", None)
                if cost is not None:
                    total_cost_usd += cost

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

    # Cost efficiency
    cost_usd: float | None = total_cost_usd if total_cost_usd > 0 else None
    spd: float | None = None
    if cost_usd is not None and cost_usd > 0:
        # Use the primary score (first metric) for cost efficiency
        primary_score = next(iter(avg_scores.values()), pass_rate)
        spd = primary_score / cost_usd

    return QuickEvalResult(
        status=status,
        pass_rate=pass_rate,
        scores=avg_scores,
        total_tokens=total_tokens,
        duration_ms=elapsed_ms,
        working_time_ms=total_working_ms,
        sample_count=total,
        estimated_cost_usd=cost_usd,
        score_per_dollar=spd,
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


# ---------------------------------------------------------------------------
# Framework-specific convenience wrappers
# ---------------------------------------------------------------------------

async def quick_eval_qitos(
    agent_module: Any,
    *,
    benchmark: str | None = None,
    scorer: Scorer | str | None = None,
    samples: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    max_tokens: int = 256,
    **qitos_kwargs: Any,
) -> QuickEvalResult:
    """Evaluate a QitOS AgentModule against a benchmark or samples.

    This is a convenience wrapper that automatically wraps the QitOS module
    via :class:`QitOSAdapter` and delegates to :func:`quick_eval`.

    Args:
        agent_module: A QitOS ``AgentModule`` instance.
        benchmark: Name of a built-in benchmark.
        scorer: A Scorer instance, a string name, or None for default.
        samples: Custom sample dicts.
        limit: Max number of samples.
        max_tokens: Token limit for agent responses.
        **qitos_kwargs: Extra config passed to ``QitOSAdapter.wrap()``.

    Returns:
        A :class:`QuickEvalResult`.

    Example::

        from snowl import quick_eval_qitos

        result = await quick_eval_qitos(
            agent_module=my_agent,
            benchmark="cybench",
            limit=10,
        )
    """
    from snowl.adapters.qitos import QitOSAdapter

    adapter = QitOSAdapter()
    agent = adapter.wrap(agent_module, **qitos_kwargs)
    return await quick_eval(
        agent=agent,
        benchmark=benchmark,
        scorer=scorer,
        samples=samples,
        limit=limit,
        max_tokens=max_tokens,
    )


async def quick_eval_langgraph(
    graph: Any,
    *,
    benchmark: str | None = None,
    scorer: Scorer | str | None = None,
    samples: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    max_tokens: int = 256,
) -> QuickEvalResult:
    """Evaluate a compiled LangGraph graph against a benchmark or samples.

    This is a convenience wrapper that automatically wraps the graph
    via :class:`LangGraphAdapter` and delegates to :func:`quick_eval`.

    Args:
        graph: A compiled LangGraph graph with an ``ainvoke()`` method.
        benchmark: Name of a built-in benchmark.
        scorer: A Scorer instance, a string name, or None for default.
        samples: Custom sample dicts.
        limit: Max number of samples.
        max_tokens: Token limit for agent responses.

    Returns:
        A :class:`QuickEvalResult`.

    Example::

        from snowl import quick_eval_langgraph

        result = await quick_eval_langgraph(
            graph=compiled_graph,
            benchmark="gaia",
            limit=10,
        )
    """
    from snowl.adapters.langgraph import LangGraphAdapter

    adapter = LangGraphAdapter()
    agent = adapter.wrap(graph)
    return await quick_eval(
        agent=agent,
        benchmark=benchmark,
        scorer=scorer,
        samples=samples,
        limit=limit,
        max_tokens=max_tokens,
    )


async def quick_eval_openai(
    client: Any,
    *,
    model: str = "gpt-4.1-mini",
    benchmark: str | None = None,
    scorer: Scorer | str | None = None,
    samples: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    max_tokens: int = 256,
) -> QuickEvalResult:
    """Evaluate an OpenAI client against a benchmark or samples.

    This is a convenience wrapper that automatically wraps the client
    via :class:`OpenAIAgentsAdapter` and delegates to :func:`quick_eval`.

    Args:
        client: An OpenAI client instance.
        model: Model name to use for evaluation.
        benchmark: Name of a built-in benchmark.
        scorer: A Scorer instance, a string name, or None for default.
        samples: Custom sample dicts.
        limit: Max number of samples.
        max_tokens: Token limit for agent responses.

    Returns:
        A :class:`QuickEvalResult`.

    Example::

        from snowl import quick_eval_openai

        result = await quick_eval_openai(
            client=openai_client,
            model="gpt-4.1-mini",
            benchmark="xstest",
            limit=10,
        )
    """
    from snowl.adapters.openai_agents import OpenAIAgentsAdapter

    adapter = OpenAIAgentsAdapter()
    agent = adapter.wrap(client, model=model)
    return await quick_eval(
        agent=agent,
        benchmark=benchmark,
        scorer=scorer,
        samples=samples,
        limit=limit,
        max_tokens=max_tokens,
    )
