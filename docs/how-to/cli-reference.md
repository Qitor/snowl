# CLI Reference

Complete reference for all `snowl` CLI commands.

---

## `snowl eval`

Run an evaluation project.

```bash
snowl eval [path] [options]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `path` | `project.yml` | Path to project.yml |

| Option | Description |
|--------|-------------|
| `--task` | Task ID selector (comma-separated) |
| `--agent` | Agent ID selector (comma-separated) |
| `--variant` | Variant ID selector (comma-separated) |
| `--scorer` | Scorer ID selector (comma-separated) |
| `--cli-ui` | Enable legacy live CLI renderer |
| `--no-ui` | Disable terminal progress output |
| `--resume` | Resume from checkpoint |
| `--rerun-failed-only` | Run only failed trials from latest run |
| `--max-running-trials N` | Max concurrently executing trials |
| `--max-container-slots N` | Max concurrent container/sandbox slots |
| `--max-builds N` | Max concurrent container builds |
| `--max-scoring-tasks N` | Max concurrent scoring tasks |
| `--keep-containers` | Preserve runtime-owned containers |
| `--keep-failed-containers` | Preserve containers only for failed trials |
| `--provider-budget PROVIDER=N` | Provider concurrency budget (repeatable) |
| `--experiment-id ID` | Optional experiment identifier |
| `--no-web-monitor` | Disable auto-start of web monitor |
| `--web-monitor-host HOST` | Web monitor host (default: 127.0.0.1) |
| `--web-monitor-port PORT` | Web monitor port (default: 8765) |

---

## `snowl retry`

Retry a previous run.

```bash
snowl retry <run_id> [options]
```

| Argument | Description |
|----------|-------------|
| `run_id` | Run ID to retry |

Supports the same runtime and UI options as `snowl eval`.

---

## `snowl bench`

Benchmark management commands.

### `snowl bench list`

List all built-in benchmark adapters.

```bash
snowl bench list
```

### `snowl bench run`

Run a built-in or external benchmark.

```bash
snowl bench run <benchmark> [options]
```

| Argument | Description |
|----------|-------------|
| `benchmark` | Benchmark adapter name |

| Option | Default | Description |
|--------|---------|-------------|
| `--project` | `project.yml` | Path to project.yml |
| `--split` | `test` | Dataset split |
| `--limit N` | None | Max samples to load |
| `--adapter` | None | External adapter spec (`module.py:object`) |
| `--adapter-arg KEY=VALUE` | None | Adapter arguments (repeatable) |
| `--benchmark-filter KEY=VALUE` | None | Row filters (repeatable) |

Supports the same runtime and UI options as `snowl eval`.

### `snowl bench check`

Validate a benchmark adapter.

```bash
snowl bench check <benchmark> [options]
```

| Option | Description |
|--------|-------------|
| `--adapter` | External adapter spec |
| `--adapter-arg KEY=VALUE` | Adapter arguments (repeatable) |

### `snowl bench scaffold`

Create a new benchmark adapter scaffold.

```bash
snowl bench scaffold <name> --out <directory>
```

| Argument | Description |
|----------|-------------|
| `name` | Benchmark name |
| `--out` | Output directory (required) |

---

## `snowl suite`

Multi-benchmark suite commands.

### `snowl suite check`

Validate a suite configuration.

```bash
snowl suite check <path>
```

### `snowl suite run`

Run a benchmark suite.

```bash
snowl suite run <path>
```

---

## `snowl report`

Generate a report from a run.

```bash
snowl report [run_id] [options]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `run_id` | `latest` | Run ID to report on |

| Option | Default | Description |
|--------|---------|-------------|
| `--project` | `.` | Project root path |
| `--format` | `html` | Output format: `html`, `json`, `markdown` |
| `--output` / `-o` | None | Output file path |

---

## `snowl compare`

Compare two runs.

```bash
snowl compare <run_id_a> <run_id_b> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--project` | `.` | Project root path |
| `--format` | `markdown` | Output format: `html`, `markdown`, `json` |
| `--output` / `-o` | None | Output file path |

---

## `snowl rescore`

Re-score a completed run.

```bash
snowl rescore [run_id] [options]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `run_id` | `latest` | Run ID to rescore |

| Option | Description |
|--------|-------------|
| `--project` | Project root path |
| `--scorer` | Scorer ID selector (comma-separated) |

---

## `snowl web`

Web monitor commands.

### `snowl web monitor`

Start the web monitor.

```bash
snowl web monitor [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--project` | `.` | Project root path |
| `--host` | `127.0.0.1` | Host to bind |
| `--port` | `8765` | Port to bind |
| `--poll-interval-sec` | `0.5` | Polling interval in seconds |

---

## `snowl examples`

Example project commands.

### `snowl examples check`

Validate example projects.

```bash
snowl examples check [path]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `path` | `examples` | Examples root path |
