"""Aggregation contracts for compare outputs and monitor-facing metric matrices.

Framework role:
- Converts per-trial `TrialOutcome` rows into stable projections consumed by reports/UI.
- Defines grouping semantics by `(task_id, agent_id, variant_id)` and mean-based metric rollups.
- V2 layer adds benchmark/domain/leaderboard rollups for risk-monitor-native display.

Runtime/usage wiring:
- `aggregate_outcomes` is called from `snowl.eval` after execution/scoring; its output is written into aggregate artifacts.
- V2 functions (`aggregate_benchmark_rows`, `aggregate_domain_rows`, etc.) are called after `aggregate_outcomes` to produce dashboard-native artifacts.
- Key formats produced here (`task::agent(::variant)` and `agent#variant`) are consumed by compare rendering and downstream tooling.

Change guardrails:
- Treat key-shape or rollup-policy changes as contract changes; update tests/docs together.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from snowl.runtime import TrialOutcome


# ---------------------------------------------------------------------------
# V1 aggregation (unchanged)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AggregateResult:
    by_task_agent: dict[str, dict[str, Any]]
    matrix: dict[str, dict[str, dict[str, float]]]


def _mean(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)


def aggregate_outcomes(outcomes: list[TrialOutcome]) -> AggregateResult:
    """Aggregate multi-metric scores by task and agent."""

    groups: dict[tuple[str, str, str], list[TrialOutcome]] = {}
    for o in outcomes:
        variant_id = str((o.task_result.payload or {}).get("variant_id") or "default")
        key = (o.task_result.task_id, o.task_result.agent_id, variant_id)
        groups.setdefault(key, []).append(o)

    by_task_agent: dict[str, dict[str, Any]] = {}
    matrix: dict[str, dict[str, dict[str, float]]] = {}

    for (task_id, agent_id, variant_id), bucket in sorted(groups.items(), key=lambda x: x[0]):
        metric_values: dict[str, list[float]] = {}
        statuses: dict[str, int] = {}
        for out in bucket:
            statuses[out.task_result.status.value] = statuses.get(out.task_result.status.value, 0) + 1
            for metric, score in out.scores.items():
                metric_values.setdefault(metric, []).append(float(score.value))

        metric_means = {metric: _mean(vals) for metric, vals in metric_values.items()}

        group_key = (
            f"{task_id}::{agent_id}"
            if variant_id == "default"
            else f"{task_id}::{agent_id}::{variant_id}"
        )
        by_task_agent[group_key] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "variant_id": variant_id,
            "model": (bucket[0].task_result.payload or {}).get("model"),
            "count": len(bucket),
            "status_counts": statuses,
            "metrics": metric_means,
        }
        label = agent_id if variant_id == "default" else f"{agent_id}#{variant_id}"
        matrix.setdefault(task_id, {})[label] = metric_means

    return AggregateResult(by_task_agent=by_task_agent, matrix=matrix)


# ---------------------------------------------------------------------------
# V2 aggregation — benchmark/domain/leaderboard rollups
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkRow:
    benchmark: str
    domain: str
    benchmark_type: str
    agent_id: str
    variant_id: str
    model: str | None
    primary_metric: str
    primary_metric_value: float
    metric_means: dict[str, float]
    sample_count: int
    metric_stderr: dict[str, float] = field(default_factory=dict)
    metric_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DomainRow:
    domain: str
    capability_score: float
    safety_score: float
    risk_index: float
    benchmark_count: int
    model_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskDomainRow:
    """Aggregated metrics for a single risk domain across benchmarks."""
    risk_domain_id: str
    display_name: str
    capability_score: float
    safety_score: float
    risk_index: float
    benchmark_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeaderboardRow:
    model: str
    domain: str
    benchmark_type: str
    primary_metric_mean: float
    rank: int
    benchmarks_evaluated: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskOverview:
    domains: list[dict[str, Any]]
    total_models: int
    total_benchmarks: int
    generated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_benchmark_rows(
    outcomes: list[TrialOutcome],
    benchmark_metadata_map: dict[str, dict[str, Any]] | None = None,
) -> list[BenchmarkRow]:
    """Aggregate outcomes by (benchmark, agent_id, variant_id) into benchmark rows.

    `benchmark_metadata_map` is a dict mapping benchmark name to metadata dict
    (with keys like domain, benchmark_type, primary_metric, higher_is_better).
    If absent, falls back to empty defaults.
    """
    from snowl.aggregator.metrics import MetricAggregator, MetricDefinition

    if benchmark_metadata_map is None:
        benchmark_metadata_map = {}

    aggregator = MetricAggregator()

    groups: dict[tuple[str, str, str], list[TrialOutcome]] = {}
    for o in outcomes:
        payload = o.task_result.payload or {}
        variant_id = str(payload.get("variant_id") or "default")
        benchmark = str(payload.get("benchmark") or "custom")
        key = (benchmark, o.task_result.agent_id, variant_id)
        groups.setdefault(key, []).append(o)

    rows: list[BenchmarkRow] = []
    for (benchmark, agent_id, variant_id), bucket in sorted(groups.items(), key=lambda x: x[0]):
        meta = benchmark_metadata_map.get(benchmark, {})
        domain = meta.get("domain", "uncategorized")
        benchmark_type = meta.get("benchmark_type", "capability")
        primary_metric = meta.get("primary_metric", "")
        higher_is_better = meta.get("higher_is_better", True)

        # Build metric definitions from benchmark metadata if available
        metric_defs_raw = meta.get("metric_definitions") or []
        metric_defs = [MetricDefinition(**d) if isinstance(d, dict) else d for d in metric_defs_raw]

        metric_values: dict[str, list[float]] = {}
        for out in bucket:
            for metric, score in out.scores.items():
                metric_values.setdefault(metric, []).append(float(score.value))

        # Use MetricAggregator for structured reports
        score_maps = [{m: v for m, v in row.items()} for row in [{k: v[i] for k, v in metric_values.items()} for i in range(max((len(v) for v in metric_values.values()), default=0))]] if metric_values else []
        reports = aggregator.aggregate(score_maps, definitions=metric_defs or None)

        metric_means = {m: _mean(v) for m, v in metric_values.items()}
        metric_stderr = {r.name: r.stderr for r in reports}

        # Build metric_metadata from reports and benchmark meta
        metric_metadata: dict[str, dict[str, Any]] = {}
        for r in reports:
            metric_metadata[r.name] = {
                "higher_is_better": r.higher_is_better,
                "aggregation": r.definition.aggregation,
                "stderr": r.stderr,
            }
            if r.definition.description:
                metric_metadata[r.name]["description"] = r.definition.description
        # Add threshold/baseline from benchmark meta if present
        metric_thresholds = meta.get("metric_thresholds") or {}
        metric_baselines = meta.get("metric_baselines") or {}
        for m_name in metric_means:
            if m_name in metric_thresholds:
                metric_metadata.setdefault(m_name, {})["threshold"] = metric_thresholds[m_name]
            if m_name in metric_baselines:
                metric_metadata.setdefault(m_name, {})["baseline"] = metric_baselines[m_name]

        primary_metric_value = 0.0
        if primary_metric and primary_metric in metric_means:
            primary_metric_value = metric_means[primary_metric]
        elif metric_means:
            first_key = next(iter(metric_means))
            primary_metric_value = metric_means[first_key]
            if not primary_metric:
                primary_metric = first_key

        model = (bucket[0].task_result.payload or {}).get("model")
        model_metadata = (bucket[0].task_result.payload or {}).get("model_metadata") or {}

        rows.append(BenchmarkRow(
            benchmark=benchmark,
            domain=domain,
            benchmark_type=benchmark_type,
            agent_id=agent_id,
            variant_id=variant_id,
            model=model,
            primary_metric=primary_metric,
            primary_metric_value=primary_metric_value,
            metric_means=metric_means,
            metric_stderr=metric_stderr,
            metric_metadata=metric_metadata,
            sample_count=len(bucket),
            metadata=model_metadata,
        ))

    return rows


def aggregate_domain_rows(benchmark_rows: list[BenchmarkRow]) -> list[DomainRow]:
    """Aggregate benchmark rows by domain into domain-level scores."""
    domain_groups: dict[str, list[BenchmarkRow]] = {}
    for row in benchmark_rows:
        domain_groups.setdefault(row.domain, []).append(row)

    rows: list[DomainRow] = []
    for domain, b_rows in sorted(domain_groups.items()):
        cap_rows = [r for r in b_rows if r.benchmark_type == "capability"]
        safety_rows = [r for r in b_rows if r.benchmark_type == "safety"]

        capability_score = _mean([r.primary_metric_value for r in cap_rows]) if cap_rows else 0.0
        safety_score = _mean([r.primary_metric_value for r in safety_rows]) if safety_rows else 0.0

        risk_index = compute_risk_index(
            capability_score=capability_score,
            safety_score=safety_score,
            has_safety=len(safety_rows) > 0,
        )

        models = {r.model for r in b_rows if r.model}

        rows.append(DomainRow(
            domain=domain,
            capability_score=round(capability_score, 4),
            safety_score=round(safety_score, 4),
            risk_index=round(risk_index, 4),
            benchmark_count=len({r.benchmark for r in b_rows}),
            model_count=len(models),
        ))

    return rows


def aggregate_risk_domain_rows(
    benchmark_rows: list[BenchmarkRow],
    *,
    risk_domain_map: dict[str, tuple[RiskDomainRow, ...]] | None = None,
    beta_config: dict[str, Any] | None = None,
) -> list[RiskDomainRow]:
    """Aggregate benchmark rows by risk domain.

    Groups benchmarks that share the same risk domain and computes
    per-domain capability, safety, and risk index scores.

    Args:
        benchmark_rows: Aggregated benchmark rows (from aggregate_benchmark_rows).
        risk_domain_map: Optional mapping of benchmark name to its RiskDomain tuples.
            If None, falls back to the benchmark registry for domain metadata.
        beta_config: Optional config for compute_risk_index weights.

    Returns:
        List of RiskDomainRow, one per unique risk domain.
    """
    from snowl.benchmarks.base import RiskDomain

    # Resolve risk domain metadata for each benchmark
    benchmark_risk_domains: dict[str, tuple[RiskDomain, ...]] = {}
    if risk_domain_map is not None:
        benchmark_risk_domains = risk_domain_map
    else:
        try:
            from snowl.benchmarks.registry import get_default_benchmark_registry
            registry = get_default_benchmark_registry()
            for entry in registry.list():
                if entry.info.risk_domains:
                    benchmark_risk_domains[entry.info.name] = entry.info.risk_domains
        except Exception:
            pass

    # Group benchmark rows by risk domain
    domain_groups: dict[str, list[BenchmarkRow]] = {}
    domain_meta: dict[str, RiskDomain] = {}
    for row in benchmark_rows:
        domains = benchmark_risk_domains.get(row.benchmark, ())
        for rd in domains:
            domain_groups.setdefault(rd.domain_id, []).append(row)
            domain_meta.setdefault(rd.domain_id, rd)

    rows: list[RiskDomainRow] = []
    for domain_id, b_rows in sorted(domain_groups.items()):
        meta = domain_meta[domain_id]
        cap_rows = [r for r in b_rows if r.benchmark_type == "capability"]
        safety_rows = [r for r in b_rows if r.benchmark_type == "safety"]

        capability_score = _mean([r.primary_metric_value for r in cap_rows]) if cap_rows else 0.0
        safety_score = _mean([r.primary_metric_value for r in safety_rows]) if safety_rows else 0.0

        risk_index = compute_risk_index(
            capability_score=capability_score,
            safety_score=safety_score,
            has_safety=len(safety_rows) > 0,
            beta_config=beta_config,
        )

        rows.append(RiskDomainRow(
            risk_domain_id=domain_id,
            display_name=meta.display_name,
            capability_score=round(capability_score, 4),
            safety_score=round(safety_score, 4),
            risk_index=round(risk_index, 4),
            benchmark_count=len({r.benchmark for r in b_rows}),
        ))

    return rows


def compute_risk_index(
    capability_score: float,
    safety_score: float,
    has_safety: bool = True,
    beta_config: dict[str, Any] | None = None,
) -> float:
    """Compute a risk index from capability and safety scores.

    For domains with safety benchmarks:
      risk = safety_weight * (1 - safety_score) + capability_weight * capability_score

    For capability-only domains:
      risk = capability_score (raw capability is the signal)

    Default weights: safety_weight=0.7, capability_weight=0.3.
    """
    if beta_config is None:
        beta_config = {}

    safety_weight = beta_config.get("safety_weight", 0.7)
    capability_weight = beta_config.get("capability_weight", 0.3)

    if has_safety:
        return safety_weight * (1.0 - safety_score) + capability_weight * capability_score
    else:
        return capability_score


def aggregate_leaderboard_rows(benchmark_rows: list[BenchmarkRow]) -> list[LeaderboardRow]:
    """Build ranked leaderboard rows per (model, domain, benchmark_type)."""
    groups: dict[tuple[str | None, str, str], list[BenchmarkRow]] = {}
    for row in benchmark_rows:
        if not row.model:
            continue
        key = (row.model, row.domain, row.benchmark_type)
        groups.setdefault(key, []).append(row)

    rows: list[LeaderboardRow] = []
    for (model, domain, benchmark_type), b_rows in sorted(groups.items()):
        metric_mean = _mean([r.primary_metric_value for r in b_rows])
        benchmarks_evaluated = len({r.benchmark for r in b_rows})
        metadata = b_rows[0].metadata if b_rows else {}

        rows.append(LeaderboardRow(
            model=model,
            domain=domain,
            benchmark_type=benchmark_type,
            primary_metric_mean=round(metric_mean, 4),
            rank=0,  # assigned below
            benchmarks_evaluated=benchmarks_evaluated,
            metadata=metadata,
        ))

    # Rank within each (domain, benchmark_type) group
    rank_groups: dict[tuple[str, str], list[LeaderboardRow]] = {}
    for row in rows:
        rank_groups.setdefault((row.domain, row.benchmark_type), []).append(row)

    for (_, _), group in rank_groups.items():
        group.sort(key=lambda r: r.primary_metric_mean, reverse=True)
        for i, row in enumerate(group, start=1):
            # Create new row with rank assigned (frozen dataclass, need new instance)
            idx = rows.index(row)
            rows[idx] = LeaderboardRow(
                model=row.model,
                domain=row.domain,
                benchmark_type=row.benchmark_type,
                primary_metric_mean=row.primary_metric_mean,
                rank=i,
                benchmarks_evaluated=row.benchmarks_evaluated,
                metadata=row.metadata,
            )

    return rows


def build_risk_overview(
    domain_rows: list[DomainRow],
    leaderboard_rows: list[LeaderboardRow],
    generated_at_utc: str = "",
) -> RiskOverview:
    """Build a top-level risk overview from domain and leaderboard rows."""
    from datetime import datetime, timezone

    if not generated_at_utc:
        generated_at_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    total_models = len({r.model for r in leaderboard_rows})
    total_benchmarks = sum(d.benchmark_count for d in domain_rows)

    return RiskOverview(
        domains=[d.to_dict() for d in domain_rows],
        total_models=total_models,
        total_benchmarks=total_benchmarks,
        generated_at_utc=generated_at_utc,
    )
