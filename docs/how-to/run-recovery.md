# Run Recovery

Retry failed runs and recover from interruptions.

---

## Manual retry

```bash
snowl retry <run_id> --project ./project.yml
```

This:

1. Checks `runtime_state.json` to ensure the run is not still active
2. Reuses the existing run directory and run ID
3. Reloads only unfinished or non-success trials

### Retry with different settings

```bash
# Increase concurrency for the retry
snowl retry <run_id> --max-running-trials 8

# Keep containers for debugging
snowl retry <run_id> --keep-failed-containers
```

---

## Rerun failed only

```bash
snowl eval ./project.yml --rerun-failed-only
```

This re-runs only the trials that failed in the latest run.

---

## Deferred auto retry

Configure automatic retry within a run in `project.yml`:

```yaml
runtime:
  recovery:
    retry_timing: deferred
    backoff_ms: 5000
    max_auto_retries_per_trial: 1
```

Behavior:

- Non-success attempts can be enqueued into a `recovery_queue`
- Retries happen after `backoff_ms` delay
- `max_auto_retries_per_trial` caps in-run auto retries
- Uses the same recovery ledger as manual retry

---

## Three layers of retry

Snowl has three layers of retry/recovery:

| Layer | Scope | Mechanism |
|-------|-------|-----------|
| Provider HTTP retry | Individual API call | Exponential backoff in `OpenAICompatibleChatClient` |
| In-run deferred auto retry | Within a single run | `recovery_queue` with configurable backoff |
| Manual run retry | Across runs | `snowl retry <run_id>` |

---

## Resume from checkpoint

```bash
snowl eval ./project.yml --resume
```

Resumes from the latest checkpoint, skipping completed trials.

You can specify a checkpoint key:

```bash
snowl eval ./project.yml --resume --checkpoint-key my_checkpoint
```

---

## Run artifacts

Every run produces a self-contained directory under `.snowl/runs/`:

```
.snowl/runs/<run_id>/
  manifest.json          # Run metadata
  plan.json              # Trial plan
  events.jsonl           # Stream of all runtime events
  outcomes.json          # Final outcomes for all trials
  aggregate.json         # Aggregated metrics
  metrics_wide.csv       # Flat CSV of all metrics
  attempts.jsonl         # Per-trial attempt records (includes retries)
  recovery.json          # Recovery ledger
  run.log                # Human-readable log
  report.html            # HTML report
  profiling.json         # Runtime profiling data
  runtime_state.json     # Current run state (active, completed, etc.)
```

---

## Container cleanup

By default, Snowl cleans up runtime-owned containers after each trial. Override
with:

```bash
# Keep all containers (for debugging)
snowl eval ./project.yml --keep-containers

# Keep only containers from failed trials
snowl eval ./project.yml --keep-failed-containers
```
