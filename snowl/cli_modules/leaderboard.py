"""Leaderboard command implementations."""

from __future__ import annotations


def _cmd_leaderboard_publish(run_dir: str) -> int:
    """Publish run results to the leaderboard using aggregate_leaderboard_rows."""
    import json
    from pathlib import Path

    from snowl.aggregator.summary import (
        BenchmarkRow,
        aggregate_leaderboard_rows,
    )

    artifacts_path = Path(run_dir)
    if not artifacts_path.exists():
        print(f"Error: directory not found: {run_dir}")
        return 1

    # Find benchmark_summary.json or aggregate.json
    summary_file = artifacts_path / "benchmark_summary.json"
    if not summary_file.exists():
        summary_file = artifacts_path / "aggregate.json"
    if not summary_file.exists():
        print(f"Error: no benchmark_summary.json or aggregate.json found in {run_dir}")
        return 1

    try:
        data = json.loads(summary_file.read_text())
    except Exception as exc:
        print(f"Error reading {summary_file}: {exc}")
        return 1

    # Extract benchmark rows from summary data
    model = data.get("model", "unknown")
    benchmark = data.get("benchmark", data.get("benchmark_name", "unknown"))
    domain = data.get("domain", "unknown")
    benchmark_type = data.get("benchmark_type", "capability")
    primary_metric = data.get("primary_metric", "success_rate")
    primary_metric_value = data.get("success_rate", data.get("primary_metric_value", 0.0))

    # Try to convert to float
    try:
        primary_metric_value = float(primary_metric_value)
    except (TypeError, ValueError):
        primary_metric_value = 0.0

    # Build BenchmarkRow and use aggregate_leaderboard_rows for ranking
    benchmark_row = BenchmarkRow(
        benchmark=benchmark,
        domain=domain,
        benchmark_type=benchmark_type,
        agent_id=data.get("agent_id", "default"),
        variant_id=data.get("variant_id", "default"),
        model=model,
        primary_metric=primary_metric,
        primary_metric_value=primary_metric_value,
        metric_means=data.get("metric_means", {primary_metric: primary_metric_value}),
        sample_count=data.get("sample_count", data.get("total", 0)),
        metadata={"run_dir": str(artifacts_path), "timestamp": data.get("timestamp", "")},
    )

    # Load existing leaderboard entries and build BenchmarkRows
    lb_path = artifacts_path.parent / "leaderboard.jsonl"
    existing_rows: list[BenchmarkRow] = []
    if lb_path.exists():
        for line in lb_path.read_text().strip().splitlines():
            try:
                entry = json.loads(line)
                existing_rows.append(BenchmarkRow(
                    benchmark=entry.get("benchmark", ""),
                    domain=entry.get("domain", "unknown"),
                    benchmark_type=entry.get("benchmark_type", "capability"),
                    agent_id=entry.get("agent_id", "default"),
                    variant_id=entry.get("variant_id", "default"),
                    model=entry.get("model"),
                    primary_metric=entry.get("primary_metric", "success_rate"),
                    primary_metric_value=float(entry.get("primary_metric_value", 0.0)),
                    metric_means=entry.get("metric_means", {}),
                    sample_count=entry.get("sample_count", 0),
                    metadata=entry.get("metadata", {}),
                ))
            except Exception:
                pass

    # Aggregate all rows (existing + new) using the proper ranking function
    all_rows = existing_rows + [benchmark_row]
    leaderboard_rows = aggregate_leaderboard_rows(all_rows)

    # Write aggregated leaderboard
    with open(lb_path, "w") as f:
        for lb_row in leaderboard_rows:
            entry = lb_row.to_dict()
            # Preserve the new row's run_dir
            entry["source_run_dir"] = str(artifacts_path)
            f.write(json.dumps(entry) + "\n")

    # Also append the raw summary for full data preservation
    raw_path = artifacts_path.parent / "leaderboard_raw.jsonl"
    with open(raw_path, "a") as f:
        f.write(json.dumps({
            "model": model,
            "benchmark": benchmark,
            "run_dir": str(artifacts_path),
            "timestamp": data.get("timestamp", ""),
            "summary": data,
        }) + "\n")

    print(f"Published {model}/{benchmark} to leaderboard ({lb_path})")
    print(f"  Leaderboard rows: {len(leaderboard_rows)}, rank computed via aggregate_leaderboard_rows()")
    return 0


def _cmd_leaderboard_list(*, domain: str | None = None, top: int = 20, cost_aware: bool = False) -> int:
    """List leaderboard entries."""
    import json
    from pathlib import Path

    # Look for leaderboard in current directory tree
    lb_paths = list(Path(".").rglob("leaderboard.jsonl"))
    if not lb_paths:
        print("No leaderboard data found. Run 'snowl leaderboard publish <run_dir>' first.")
        return 0

    entries: list[dict] = []
    for lb_path in lb_paths:
        for line in lb_path.read_text().strip().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    if domain:
        entries = [e for e in entries if domain in str(e.get("summary", {}).get("domain", ""))]

    # Sort by primary metric if available
    def _sort_key(e: dict) -> float:
        s = e.get("summary", {})
        # Try common metric keys
        for k in ("success_rate", "accuracy", "score", "primary_metric_value"):
            v = s.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0

    entries.sort(key=_sort_key, reverse=True)

    if not entries:
        print("No leaderboard entries found.")
        return 0

    if cost_aware:
        print(f"{'Rank':<5} {'Model':<30} {'Benchmark':<20} {'Score':<10} {'CostEff':<12}")
        print("-" * 77)
        for i, entry in enumerate(entries[:top], start=1):
            model = entry.get("model", "?")[:28]
            benchmark = entry.get("benchmark", "?")[:18]
            score = _sort_key(entry)
            ce = entry.get("cost_efficiency")
            ce_str = f"{ce:.6f}" if ce is not None else "N/A"
            print(f"{i:<5} {model:<30} {benchmark:<20} {score:<10.4f} {ce_str:<12}")
    else:
        print(f"{'Rank':<5} {'Model':<30} {'Benchmark':<20} {'Score':<10}")
        print("-" * 65)
        for i, entry in enumerate(entries[:top], start=1):
            model = entry.get("model", "?")[:28]
            benchmark = entry.get("benchmark", "?")[:18]
            score = _sort_key(entry)
            print(f"{i:<5} {model:<30} {benchmark:<20} {score:<10.4f}")

    return 0


def _cmd_leaderboard_compare(run_dir_a: str, run_dir_b: str) -> int:
    """Compare two runs on the leaderboard."""
    import json
    from pathlib import Path

    def _load_summary(run_dir: str) -> dict | None:
        p = Path(run_dir)
        for name in ("benchmark_summary.json", "aggregate.json"):
            f = p / name
            if f.exists():
                try:
                    return json.loads(f.read_text())
                except Exception:
                    pass
        return None

    summary_a = _load_summary(run_dir_a)
    summary_b = _load_summary(run_dir_b)

    if not summary_a:
        print(f"Error: no summary found in {run_dir_a}")
        return 1
    if not summary_b:
        print(f"Error: no summary found in {run_dir_b}")
        return 1

    print(f"{'Metric':<25} {'Run A':<15} {'Run B':<15} {'Delta':<10}")
    print("-" * 65)

    # Compare common numeric metrics
    all_keys = set(summary_a.keys()) | set(summary_b.keys())
    for key in sorted(all_keys):
        va = summary_a.get(key)
        vb = summary_b.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta = va - vb
            sign = "+" if delta > 0 else ""
            print(f"{key:<25} {va:<15.4f} {vb:<15.4f} {sign}{delta:<10.4f}")

    return 0
