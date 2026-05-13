# Getting Started

Install Snowl, run your first evaluation, and understand what you get.

---

## Installation

```bash
pip install -e .
```

Snowl requires Python 3.10+. Core dependencies include `httpx`, `rich`,
`PyYAML`, and `Jinja2`.

For optional benchmark asset downloads (Hugging Face datasets, etc.):

```bash
pip install -e ".[safety_assets]"
```

---

## Run your first eval

```bash
# List available benchmarks
snowl bench list

# Run StrongReject safety evaluation
snowl eval examples/strongreject-official/project.yml

# Run with a sample limit (faster for testing)
snowl eval examples/strongreject-official/project.yml --limit 5
```

The terminal shows a Rich-panel TUI with colored progress, model I/O,
and scorer results.

---

## Run a specific benchmark

```bash
snowl bench run strongreject \
  --project examples/strongreject-official/project.yml \
  --split test \
  --limit 10
```

---

## What you get from each run

Every run produces a self-contained directory under `.snowl/runs/`:

```
.snowl/runs/<run_id>/
  manifest.json          # Run metadata (project, models, timestamps)
  plan.json              # Trial plan (task × agent × sample matrix)
  events.jsonl           # Stream of all runtime events
  outcomes.json          # Final outcomes for all trials
  aggregate.json         # Aggregated metrics by task/agent
  metrics_wide.csv       # Flat CSV of all metrics
  run.log                # Human-readable log
  report.html            # HTML report
```

These artifacts support:

- Reproducing failed trials
- Building dashboards
- Comparing model variants
- Debugging benchmark environments
- Auditing safety regressions

---

## Next steps

- [Quick Start](quick-start.md) — build a complete evaluation project from scratch
- [Project Anatomy](../tutorials/project-anatomy.md) — understand the four-file structure
- [Benchmark Catalog](../benchmarks/index.md) — browse available benchmarks
