"""Jinja2-templated HTML report rendering.

Framework role:
- Renders evaluation reports from V1 (AggregateResult) and V2 (BenchmarkRow, DomainRow,
  LeaderboardRow) aggregate data into full HTML with charts and tables.

Runtime/usage wiring:
- Called from ``RunArtifactStore._html_report()`` and ``snowl report`` CLI command.
"""

from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    return env


def _svg_bar_chart(
    data: dict[str, dict[str, float]],
    *,
    width: int = 600,
    bar_height: int = 28,
    gap: int = 4,
    margin_left: int = 120,
    margin_right: int = 60,
    margin_top: int = 20,
    margin_bottom: int = 30,
) -> str:
    """Generate an inline SVG horizontal bar chart.

    Args:
        data: {agent_label: {metric_name: value}} — all values assumed 0..1.
        width: Total SVG width.
        bar_height: Height of each bar.
        gap: Vertical gap between bars.
        margin_left: Space for agent labels.
        margin_right: Space for value labels.
        margin_top: Top margin.
        margin_bottom: Bottom margin.
    """
    if not data:
        return '<p class="no-data">No data</p>'

    agents = sorted(data.keys())
    metrics = sorted({m for row in data.values() for m in row})
    if not metrics:
        return '<p class="no-data">No metrics</p>'

    # We'll show one chart per metric
    charts: list[str] = []
    for metric in metrics:
        entries = [(agent, data[agent].get(metric, 0.0)) for agent in agents if metric in data[agent]]
        if not entries:
            continue

        chart_h = margin_top + len(entries) * (bar_height + gap) + margin_bottom
        chart_w = width

        parts = [
            f'<svg class="bar-chart" viewBox="0 0 {chart_w} {chart_h}" '
            f'xmlns="http://www.w3.org/2000/svg">',
            f'<text x="{margin_left + (chart_w - margin_left - margin_right) // 2}" y="{margin_top - 4}" '
            f'text-anchor="middle" class="chart-title">{html_lib.escape(metric)}</text>',
        ]

        plot_w = chart_w - margin_left - margin_right
        for i, (agent, value) in enumerate(entries):
            y = margin_top + i * (bar_height + gap)
            bar_w = max(1, int(value * plot_w)) if plot_w > 0 else 0
            parts.append(
                f'<text x="{margin_left - 6}" y="{y + bar_height // 2 + 4}" '
                f'text-anchor="end" class="bar-label">{html_lib.escape(agent)}</text>'
            )
            parts.append(
                f'<rect x="{margin_left}" y="{y}" width="{bar_w}" height="{bar_height}" '
                f'class="bar" rx="3"/>'
            )
            parts.append(
                f'<text x="{margin_left + bar_w + 4}" y="{y + bar_height // 2 + 4}" '
                f'class="bar-value">{value:.3f}</text>'
            )

        parts.append('</svg>')
        charts.append('\n'.join(parts))

    return '\n'.join(charts)


def _color_class(value: float, higher_is_better: bool, threshold: float = 0.5) -> str:
    """Return a CSS class name based on value vs threshold and direction."""
    if higher_is_better:
        return "metric-good" if value >= threshold else "metric-bad"
    return "metric-good" if value <= threshold else "metric-bad"


def render_report(
    *,
    summary: Any,
    aggregate: Any,
    diagnostics_index: list[dict[str, Any]],
    benchmark_rows: list[Any] | None = None,
    domain_rows: list[Any] | None = None,
    leaderboard_rows: list[Any] | None = None,
    run_id: str = "",
    experiment_id: str | None = None,
) -> str:
    """Render a full HTML report from aggregate data.

    Args:
        summary: EvalSummary-like object with total/success/incorrect/error/limit_exceeded/cancelled.
        aggregate: AggregateResult from aggregate_outcomes().
        diagnostics_index: List of diagnostic metadata dicts.
        benchmark_rows: Optional list of BenchmarkRow from aggregate_benchmark_rows().
        domain_rows: Optional list of DomainRow from aggregate_domain_rows().
        leaderboard_rows: Optional list of LeaderboardRow from aggregate_leaderboard_rows().
        run_id: Run identifier.
        experiment_id: Optional experiment identifier.

    Returns:
        Complete HTML string.
    """
    env = _jinja_env()

    # Build chart data from aggregate.matrix: {task_id: {agent_label: {metric: float}}}
    chart_data: dict[str, dict[str, float]] = {}
    for task_id in sorted(aggregate.matrix.keys()):
        for agent_label, metrics in aggregate.matrix[task_id].items():
            for metric, value in metrics.items():
                chart_data.setdefault(metric, {})[agent_label] = value

    bar_charts_svg = {metric: _svg_bar_chart({k: {metric: v} for k, v in agents.items()})
                      for metric, agents in chart_data.items()}
    # Flatten: one chart per metric showing all agents
    bar_charts_svg = {}
    for metric, agents in chart_data.items():
        bar_charts_svg[metric] = _svg_bar_chart({agent: {metric: val} for agent, val in agents.items()})

    # Build domain risk table data
    domain_table = []
    if domain_rows:
        for dr in domain_rows:
            domain_table.append({
                "domain": dr.domain,
                "capability_score": dr.capability_score,
                "safety_score": dr.safety_score,
                "risk_index": dr.risk_index,
                "benchmark_count": dr.benchmark_count,
                "model_count": dr.model_count,
            })

    # Build benchmark comparison table from V2 data if available
    benchmark_table = []
    metric_metadata_map: dict[str, dict[str, Any]] = {}
    if benchmark_rows:
        for br in benchmark_rows:
            row = {
                "benchmark": br.benchmark,
                "domain": br.domain,
                "benchmark_type": br.benchmark_type,
                "agent_id": br.agent_id,
                "variant_id": br.variant_id,
                "model": br.model or "",
                "primary_metric": br.primary_metric,
                "primary_metric_value": br.primary_metric_value,
                "metric_means": br.metric_means,
                "metric_stderr": getattr(br, "metric_stderr", {}),
                "sample_count": br.sample_count,
            }
            benchmark_table.append(row)
            if hasattr(br, "metric_metadata"):
                metric_metadata_map.update(br.metric_metadata)

    # Build leaderboard table
    leaderboard_table = []
    if leaderboard_rows:
        for lr in leaderboard_rows:
            leaderboard_table.append({
                "rank": lr.rank,
                "model": lr.model,
                "domain": lr.domain,
                "benchmark_type": lr.benchmark_type,
                "primary_metric_mean": lr.primary_metric_mean,
                "benchmarks_evaluated": lr.benchmarks_evaluated,
            })

    template = env.get_template("report.html.j2")
    return template.render(
        run_id=run_id,
        experiment_id=experiment_id or "",
        summary=summary,
        aggregate=aggregate,
        diagnostics_index=diagnostics_index,
        bar_charts=bar_charts_svg,
        domain_table=domain_table,
        benchmark_table=benchmark_table,
        leaderboard_table=leaderboard_table,
        metric_metadata=metric_metadata_map,
        color_class=_color_class,
    )
