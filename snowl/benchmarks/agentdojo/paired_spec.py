"""Paired evaluation aggregation for AgentDojo clean-vs-attacked comparison.

Framework role:
- Pairs clean and attacked trial outcomes by ``pair_id`` in sample metadata.
- Computes paired metrics: utility preserved under attack, attack success rate.

Runtime/usage wiring:
- Called after aggregation in the report/benchmark summary pipeline.
- Results included in benchmark summary artifacts.

Change guardrails:
- PairedEvaluationResult is a data contract; changes affect report output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl.runtime import TrialOutcome


@dataclass(frozen=True)
class PairedEvaluationResult:
    """Result of pairing a clean and attacked trial outcome."""

    pair_id: str
    suite: str
    user_task_id: str
    clean_utility: float
    attacked_utility: float
    attacked_security: float
    utility_preserved: float   # attacked_utility / max(clean_utility, epsilon)
    attack_success_rate: float  # 1 - attacked_security

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "suite": self.suite,
            "user_task_id": self.user_task_id,
            "clean_utility": round(self.clean_utility, 4),
            "attacked_utility": round(self.attacked_utility, 4),
            "attacked_security": round(self.attacked_security, 4),
            "utility_preserved": round(self.utility_preserved, 4),
            "attack_success_rate": round(self.attack_success_rate, 4),
        }


_EPSILON = 1e-6


def compute_paired_results(
    outcomes: list[TrialOutcome],
) -> list[PairedEvaluationResult]:
    """Pair clean and attacked outcomes by pair_id and compute paired metrics.

    Expects outcomes to have ``run_mode`` ("clean" or "attacked") and
    ``pair_id`` in their task_result.payload (populated from sample metadata
    by the planning/discovery pipeline).

    Args:
        outcomes: List of TrialOutcome from an AgentDojo evaluation run.

    Returns:
        List of PairedEvaluationResult, one per unique pair_id that has both
        a clean and attacked outcome.
    """
    # Group by (pair_id, run_mode)
    groups: dict[str, dict[str, TrialOutcome]] = {}
    for outcome in outcomes:
        payload = outcome.task_result.payload or {}
        pair_id = str(payload.get("pair_id", ""))
        run_mode = str(payload.get("run_mode", ""))
        if not pair_id or not run_mode:
            continue
        groups.setdefault(pair_id, {})[run_mode] = outcome

    results: list[PairedEvaluationResult] = []
    for pair_id in sorted(groups):
        pair = groups[pair_id]
        clean = pair.get("clean")
        attacked = pair.get("attacked")
        if clean is None or attacked is None:
            continue

        clean_utility = float(clean.scores.get("agentdojo_utility", clean.scores.get("utility", 0.0)).value)
        attacked_utility = float(attacked.scores.get("agentdojo_utility", attacked.scores.get("utility", 0.0)).value)
        attacked_security = float(attacked.scores.get("agentdojo_security", attacked.scores.get("security", 0.0)).value)

        utility_preserved = attacked_utility / max(clean_utility, _EPSILON)
        attack_success_rate = 1.0 - attacked_security

        suite = str(clean.task_result.payload.get("suite", ""))
        user_task_id = str(clean.task_result.payload.get("user_task_id", ""))

        results.append(PairedEvaluationResult(
            pair_id=pair_id,
            suite=suite,
            user_task_id=user_task_id,
            clean_utility=clean_utility,
            attacked_utility=attacked_utility,
            attacked_security=attacked_security,
            utility_preserved=utility_preserved,
            attack_success_rate=attack_success_rate,
        ))

    return results


def compute_paired_summary(paired_results: list[PairedEvaluationResult]) -> dict[str, Any]:
    """Compute aggregate paired evaluation metrics across all pairs.

    Args:
        paired_results: List of PairedEvaluationResult.

    Returns:
        Dict with mean utility_preserved, mean attack_success_rate, pair_count.
    """
    if not paired_results:
        return {"pair_count": 0, "mean_utility_preserved": 0.0, "mean_attack_success_rate": 0.0}

    mean_preserved = sum(r.utility_preserved for r in paired_results) / len(paired_results)
    mean_asr = sum(r.attack_success_rate for r in paired_results) / len(paired_results)

    return {
        "pair_count": len(paired_results),
        "mean_utility_preserved": round(mean_preserved, 4),
        "mean_attack_success_rate": round(mean_asr, 4),
    }
