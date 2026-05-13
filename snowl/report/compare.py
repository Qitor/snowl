"""Run comparison logic — compute diffs between two eval runs.

Framework role:
- Provides ``compare_runs`` to compute per-metric deltas between two aggregate results.
- Provides ``render_compare_html`` for HTML diff reports.

Runtime/usage wiring:
- Called from ``snowl compare`` CLI command.
"""

from __future__ import annotations

import html as html_lib
from typing import Any


def compare_runs(
    agg_a: dict[str, Any],
    agg_b: dict[str, Any],
    *,
    benchmark_rows_a: list[dict[str, Any]] | None = None,
    benchmark_rows_b: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare two aggregate results and return per-metric deltas.

    Args:
        agg_a: Aggregate JSON from run A (contains "matrix" key).
        agg_b: Aggregate JSON from run B (contains "matrix" key).
        benchmark_rows_a: Optional V2 benchmark summary rows from run A.
        benchmark_rows_b: Optional V2 benchmark summary rows from run B.

    Returns:
        Dict with "deltas" (list of per-metric diffs), "summary" counts.
    """
    matrix_a: dict[str, dict[str, dict[str, float]]] = agg_a.get("matrix", {})
    matrix_b: dict[str, dict[str, dict[str, float]]] = agg_b.get("matrix", {})

    deltas: list[dict[str, Any]] = []
    improved = 0
    regressed = 0
    unchanged = 0

    # Compare V1 matrix: {task_id: {agent_label: {metric: value}}}
    all_keys = set()
    for task_id in set(matrix_a.keys()) | set(matrix_b.keys()):
        agents_a = matrix_a.get(task_id, {})
        agents_b = matrix_b.get(task_id, {})
        for agent_label in set(agents_a.keys()) | set(agents_b.keys()):
            metrics_a = agents_a.get(agent_label, {})
            metrics_b = agents_b.get(agent_label, {})
            for metric in set(metrics_a.keys()) | set(metrics_b.keys()):
                val_a = metrics_a.get(metric)
                val_b = metrics_b.get(metric)
                if val_a is None or val_b is None:
                    continue
                delta = val_b - val_a
                key = f"{task_id}::{agent_label}"
                direction = "unchanged" if abs(delta) < 1e-6 else ("improved" if delta > 0 else "regressed")
                if direction == "improved":
                    improved += 1
                elif direction == "regressed":
                    regressed += 1
                else:
                    unchanged += 1
                deltas.append({
                    "key": key,
                    "metric": metric,
                    "value_a": val_a,
                    "value_b": val_b,
                    "delta": delta,
                    "direction": direction,
                })

    # Also compare V2 benchmark rows if available
    if benchmark_rows_a and benchmark_rows_b:
        br_a_map: dict[str, dict[str, float]] = {}
        for row in benchmark_rows_a:
            key = f"{row.get('benchmark', '')}::{row.get('agent_id', '')}#{row.get('variant_id', 'default')}"
            br_a_map[key] = row.get("metric_means", {})
        br_b_map: dict[str, dict[str, float]] = {}
        for row in benchmark_rows_b:
            key = f"{row.get('benchmark', '')}::{row.get('agent_id', '')}#{row.get('variant_id', 'default')}"
            br_b_map[key] = row.get("metric_means", {})

        for key in set(br_a_map.keys()) | set(br_b_map.keys()):
            metrics_a = br_a_map.get(key, {})
            metrics_b = br_b_map.get(key, {})
            for metric in set(metrics_a.keys()) | set(metrics_b.keys()):
                val_a = metrics_a.get(metric)
                val_b = metrics_b.get(metric)
                if val_a is None or val_b is None:
                    continue
                # Skip if already covered by V1 matrix comparison
                v1_key = f"v2::{key}::{metric}"
                delta = val_b - val_a
                direction = "unchanged" if abs(delta) < 1e-6 else ("improved" if delta > 0 else "regressed")
                if direction == "improved":
                    improved += 1
                elif direction == "regressed":
                    regressed += 1
                else:
                    unchanged += 1

    return {
        "deltas": deltas,
        "summary": {
            "improved": improved,
            "regressed": regressed,
            "unchanged": unchanged,
        },
    }


def render_compare_html(diff: dict[str, Any], *, run_id_a: str = "", run_id_b: str = "") -> str:
    """Render a comparison diff as a standalone HTML page."""
    summary = diff.get("summary", {})
    deltas = diff.get("deltas", [])

    delta_rows = []
    for d in deltas:
        color = "green" if d["direction"] == "improved" else ("red" if d["direction"] == "regressed" else "gray")
        delta_rows.append(
            f'<tr><td>{html_lib.escape(d["key"])}</td>'
            f'<td>{html_lib.escape(d["metric"])}</td>'
            f'<td class="num">{d["value_a"]:.4f}</td>'
            f'<td class="num">{d["value_b"]:.4f}</td>'
            f'<td class="num" style="color:{color}">{d["delta"]:+.4f}</td>'
            f'<td style="color:{color}">{d["direction"]}</td></tr>'
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Snowl Compare</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Menlo,Consolas,monospace;padding:24px;max-width:1000px;margin:0 auto;line-height:1.5}}
h1{{font-size:1.4rem}} .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}}
.card{{border:1px solid #e0e0e0;border-radius:6px;padding:12px;text-align:center}}
.card .value{{font-size:1.3rem;font-weight:700}} .card .label{{font-size:0.75rem;color:#888;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:0.85rem}} th,td{{border:1px solid #e0e0e0;padding:6px 10px;text-align:left}}
th{{background:#f5f5f5;font-weight:600}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
</style></head><body>
<h1>Compare: {html_lib.escape(run_id_a)} vs {html_lib.escape(run_id_b)}</h1>
<div class="cards">
<div class="card"><div class="value" style="color:green">{summary.get("improved", 0)}</div><div class="label">Improved</div></div>
<div class="card"><div class="value" style="color:red">{summary.get("regressed", 0)}</div><div class="label">Regressed</div></div>
<div class="card"><div class="value" style="color:gray">{summary.get("unchanged", 0)}</div><div class="label">Unchanged</div></div>
</div>
<table><thead><tr><th>Key</th><th>Metric</th><th>Run A</th><th>Run B</th><th>Delta</th><th>Direction</th></tr></thead>
<tbody>{''.join(delta_rows) if delta_rows else '<tr><td colspan="6" style="color:#888">No comparable metrics</td></tr>'}</tbody></table>
</body></html>"""
