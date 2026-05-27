"""Score phase for single-trial execution.

Hosts ``score_trial_phase`` and the separated-verifier helper ``_score_in_verifier``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from snowl.core.scorer import ScoreContext, validate_scores
from snowl.core.task_result import ErrorInfo, TaskResult, TaskStatus
from snowl.ui.contracts import build_score_explanations

from ._shared import (
    PartialTrialResult,
    PreparedTrial,
    TrialOutcome,
    TrialRequest,
    _emit_factory,
    _json_safe,
)


async def _score_in_verifier(
    executor: Any,
    scorer: Any,
    task_result: Any,
    trace: dict[str, Any],
    context: Any,
    *,
    verifier_spec: Any,
    emit: Any,
) -> dict[str, Any] | None:
    """Run a scorer's verification in the separated verifier container.

    Uses the ``SEPARATED_SCORER_REGISTRY`` to find the appropriate
    separated scorer, resolves its command, runs it in the container,
    and converts the result into a ScoreMap.
    """
    from snowl.scorer.separated import SEPARATED_SCORER_REGISTRY

    scorer_id = getattr(scorer, "scorer_id", "scorer")

    # Look up the separated scorer class
    separated_cls = SEPARATED_SCORER_REGISTRY.get(scorer_id)
    if separated_cls is None:
        # Scorer doesn't support separated execution -- fall back to shared
        emit({
            "event": "runtime.verifier.no_separated_scorer",
            "phase": "score",
            "scorer_id": scorer_id,
        })
        if hasattr(scorer, "ascore") and callable(scorer.ascore):
            return await scorer.ascore(task_result, trace, context)
        return await asyncio.to_thread(scorer.score, task_result, trace, context)

    # Instantiate the separated scorer
    separated_scorer = separated_cls()

    # Resolve the command to run in the verifier container
    command = separated_scorer.resolve_command(context)
    if not command:
        emit({
            "event": "runtime.verifier.no_command",
            "phase": "score",
            "scorer_id": scorer_id,
        })
        return None

    # Run the command in the verifier container
    result = await executor.run_command(
        command,
        workdir="/workspace",
        timeout_seconds=verifier_spec.timeout_seconds,
    )

    # Convert the verifier result into a ScoreMap
    return separated_scorer.score_from_result(result)


async def score_trial_phase(prepared: PreparedTrial | TrialRequest, partial: PartialTrialResult) -> TrialOutcome:
    """Apply the scorer(s) to a partial trial result and finalize status."""
    request = prepared.request if isinstance(prepared, PreparedTrial) else prepared
    task_result = partial.task_result
    trace = partial.trace
    score_context = partial.score_context
    variant_id = str(getattr(request.agent, "variant_id", "default"))
    emit = _emit_factory(request)

    if isinstance(prepared, PreparedTrial) and prepared.failed_partial is partial:
        return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    # Use scorers list (backward compat: __post_init__ wraps single scorer)
    scorers = request.scorers
    all_scores: dict[str, Any] = {}
    scorer_error: Exception | None = None

    # -- Separated verifier setup --
    verifier_spec = request.task.verifier_spec
    verifier_executor = None
    if verifier_spec is not None and verifier_spec.mode.value == "separate":
        try:
            from snowl.runtime.separated_verifier import SeparatedVerifierExecutor
            workspace_dir = None
            if isinstance(prepared, PreparedTrial) and prepared.workspace_session is not None:
                workspace_dir = prepared.workspace_session.workspace_dir
            verifier_executor = SeparatedVerifierExecutor(
                spec=verifier_spec,
                run_id=getattr(request, "run_id", None),
                trial_id=getattr(request, "trial_id", None),
                emit=emit,
            )
            await verifier_executor.prepare()
            if workspace_dir:
                await verifier_executor.transfer_artifacts(workspace_dir=workspace_dir)
        except Exception as exc:
            emit({
                "event": "runtime.verifier.fallback",
                "phase": "score",
                "message": str(exc),
            })
            verifier_executor = None  # Fallback to shared mode

    for scorer in scorers:
        scorer_id = getattr(scorer, "scorer_id", "scorer")

        # Determine if this scorer should run in separated verifier
        should_separate = (
            verifier_executor is not None
            and verifier_spec is not None
            and (
                not verifier_spec.priority_scorers
                or scorer_id in verifier_spec.priority_scorers
            )
        )

        if should_separate:
            try:
                scores = await _score_in_verifier(
                    verifier_executor, scorer, task_result, trace, score_context,
                    verifier_spec=verifier_spec,
                    emit=emit,
                )
                if scores:
                    validate_scores(scores)
                    all_scores.update(scores)
            except Exception as exc:
                scorer_error = exc
                emit({
                    "event": "runtime.trial.error",
                    "phase": "score",
                    "code": "verifier_scorer_error",
                    "message": str(exc),
                    "task_id": task_result.task_id,
                    "scorer_id": scorer_id,
                })
            continue  # Skip in-process scoring for this scorer

        try:
            emit(
                {
                    "event": "runtime.scorer.start",
                    "phase": "scorer",
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                }
            )
            scorer_context = score_context
            if scorer_id == "toolemu" and getattr(scorer, "use_official_evaluator", False):
                scorer_context = ScoreContext(
                    task_id=score_context.task_id,
                    agent_id=score_context.agent_id,
                    sample_id=score_context.sample_id,
                    task_metadata=score_context.task_metadata,
                    sample_metadata={
                        **score_context.sample_metadata,
                        "__snowl_emit_event": emit,
                        "__snowl_variant_id": variant_id,
                    },
                )
            if hasattr(scorer, "ascore") and callable(scorer.ascore):
                scores = await scorer.ascore(task_result, trace, scorer_context)
            else:
                scores = await asyncio.to_thread(scorer.score, task_result, trace, scorer_context)
            validate_scores(scores)
            all_scores.update(scores)
            emit(
                {
                    "event": "runtime.scorer.finish",
                    "phase": "scorer",
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                    "metrics": {k: float(v.value) for k, v in scores.items()},
                    "explanations": [
                        {
                            "metric": e.metric,
                            "value": e.value,
                            "evidence": list(e.evidence),
                            "reason": e.reason,
                            "raw": dict(e.raw),
                        }
                        for e in build_score_explanations(
                            scores,
                            trace=trace,
                            task_result={"status": task_result.status.value},
                        )
                    ],
                }
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            scorer_error = exc
            emit(
                {
                    "event": "runtime.trial.error",
                    "phase": "score",
                    "code": "scorer_error",
                    "message": str(exc),
                    "task_id": task_result.task_id,
                    "agent_id": task_result.agent_id,
                    "variant_id": variant_id,
                    "sample_id": task_result.sample_id,
                    "scorer_id": scorer_id,
                }
            )
            # If only one scorer and it failed, treat as error; otherwise continue
            if len(scorers) == 1:
                task_result = TaskResult(
                    task_id=task_result.task_id,
                    agent_id=task_result.agent_id,
                    sample_id=task_result.sample_id,
                    seed=task_result.seed,
                    status=TaskStatus.ERROR,
                    final_output=task_result.final_output,
                    timing=task_result.timing,
                    usage=task_result.usage,
                    error=ErrorInfo(code="scorer_error", message=str(exc), retryable=False),
                    artifacts=task_result.artifacts,
                    payload=task_result.payload,
                )
                return TrialOutcome(task_result=task_result, scores={}, trace=trace)

    # -- Separated verifier teardown --
    if verifier_executor is not None:
        try:
            await verifier_executor.teardown()
        except Exception:
            pass

    accuracy = all_scores.get("accuracy")
    if (
        task_result.status == TaskStatus.SUCCESS
        and accuracy is not None
        and float(getattr(accuracy, "value", 1.0)) < 1.0
    ):
        task_result = TaskResult(
            task_id=task_result.task_id,
            agent_id=task_result.agent_id,
            sample_id=task_result.sample_id,
            seed=task_result.seed,
            status=TaskStatus.INCORRECT,
            final_output=task_result.final_output,
            timing=task_result.timing,
            usage=task_result.usage,
            error=task_result.error,
            artifacts=task_result.artifacts,
            payload=task_result.payload,
        )
    emit(
        {
            "event": "runtime.trial.finish",
            "phase": "score",
            "task_id": task_result.task_id,
            "agent_id": task_result.agent_id,
            "variant_id": variant_id,
            "sample_id": task_result.sample_id,
            "status": task_result.status.value,
            "message": str((task_result.final_output or {}).get("content") or "")[:240],
            "payload": {
                "final_output": _json_safe(task_result.final_output),
                "scores": {k: float(v.value) for k, v in all_scores.items()},
            },
        }
    )

    return TrialOutcome(task_result=task_result, scores=all_scores, trace=trace)
