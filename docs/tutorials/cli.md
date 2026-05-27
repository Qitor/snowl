# CLI Reference

Running and managing evaluations from the command line.

---

## snowl eval

Run a full evaluation from a project directory:

```bash
snowl eval /path/to/project
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--max-running` | 4 | Maximum concurrent trials |
| `--limit` | None | Limit number of samples |
| `--output-dir` | `.snowl/runs/` | Artifact output directory |
| `--dry-run` | False | Show plan without executing |

## snowl quick-eval

Run a quick evaluation without a project directory:

```bash
snowl quick-eval --benchmark strongreject --limit 10 --scorer includes
```

This is the CLI equivalent of `quick_eval_sync()`.

## snowl check

Validate your project configuration and environment:

```bash
snowl check /path/to/project
```

Checks:

- Project YAML syntax and required fields
- Agent, task, and scorer modules load correctly
- API key availability
- Benchmark adapter resolution
- Tool middleware compatibility
- Architecture boundary compliance

## snowl leaderboard

Generate a cost-aware leaderboard from evaluation results:

```bash
snowl leaderboard --run-dir .snowl/runs/latest
```

Options:

| Flag | Description |
|------|-------------|
| `--sort-by` | Primary sort metric (default: `pass_rate`) |
| `--cost-aware` | Include score-per-dollar ranking |
| `--format` | Output format: `table`, `json`, `csv` |

## snowl registry

List available benchmarks and their metadata:

```bash
snowl registry list
snowl registry info strongreject
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | API key for OpenAI-compatible endpoints |
| `OPENAI_BASE_URL` | Custom endpoint URL |
| `OPENAI_MODEL` | Default model name |
| `SNOWL_RUN_DIR` | Override default run output directory |

## Project structure

A Snowl project is a directory with:

```
my-project/
  project.yml    # Configuration
  agent.py       # Agent definition
  task.py        # Task/benchmark definition
  scorer.py      # Scorer definition (optional)
```

See [Project Anatomy](project-anatomy.md) for the full field reference.

## Next steps

- [First Evaluation](first-eval.md) -- run your first eval programmatically
- [Project Anatomy](project-anatomy.md) -- every field in `project.yml`
- [Runtime](runtime.md) -- concurrency and execution modes
