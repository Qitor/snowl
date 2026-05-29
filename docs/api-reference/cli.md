# CLI Reference

## snowl eval

Run evaluations on a project directory.

```bash
snowl eval <path> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--task` | all | Task name filter |
| `--agent` | default | Agent variant to use |
| `--scorer` | default | Scorer to use |
| `--resume` | false | Resume interrupted run |
| `--rerun-failed-only` | false | Re-run only failed trials |
| `--max-running-trials` | 4 | Max concurrent trials |
| `--keep-containers` | false | Keep containers after evaluation |
| `--no-ui` | false | Disable terminal UI |
| `--no-web-monitor` | false | Disable web monitor |

## snowl retry

Retry failed trials from a previous run.

```bash
snowl retry <run_id> --project <path> [options]
```

## snowl bench

Benchmark management commands.

### snowl bench list

List available benchmarks.

### snowl bench run

```bash
snowl bench run <benchmark> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--split` | official | Dataset split |
| `--limit` | all | Max samples |
| `--agent` | default | Agent variant |
| `--adapter` | — | Adapter class path |

### snowl bench check

Validate a benchmark adapter.

```bash
snowl bench check <benchmark>
```

### snowl bench scaffold

Create a new benchmark adapter scaffold.

```bash
snowl bench scaffold <name> --out <directory>
```

## snowl quick-eval

One-command evaluation without project setup.

```bash
snowl quick-eval --agent <agent_spec> --benchmark <name> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--agent` | required | Agent (callable path or `lambda:response`) |
| `--benchmark` | required | Benchmark name |
| `--samples` | all | Number of samples |
| `--scorer` | default | Scorer to use |
| `--limit` | all | Max samples |

## snowl registry

Registry inspection commands.

### snowl registry list

List registered benchmarks, adapters, and providers.

```bash
snowl registry list --kind <benchmarks|adapters|providers>
```

### snowl registry doctor

Diagnose registry issues and missing dependencies.

### snowl registry info

Show detailed info about a registered item.

## snowl leaderboard

Leaderboard management.

### snowl leaderboard publish

Publish run results to the leaderboard.

```bash
snowl leaderboard publish <run_dir>
```

### snowl leaderboard list

View leaderboard rankings.

```bash
snowl leaderboard list [--domain <domain>] [--top N] [--cost-aware]
```

### snowl leaderboard compare

Compare two runs head-to-head.

```bash
snowl leaderboard compare <run_dir_a> <run_dir_b>
```

## snowl report

Generate a report from a run.

```bash
snowl report <run_id> [--format json|markdown] [--output <file>]
```

## snowl check

Verify Snowl installation and dependencies.

```bash
snowl check
```

Checks Python version, installed packages, API key availability, and adapter conformance.
