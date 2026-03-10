# terminalbench-official

Official Terminal-Bench example using Snowl's YAML-first multi-model authoring.

Files:

- `project.yml`: provider, tested models, eval code paths, runtime budgets, terminalbench settings
- `task.py`: loads tasks from `references/terminal-bench/original-tasks`
- `agent.py`: builds one `TerminusOfficialAgent` per model entry
- `scorer.py`: parses task output / pytest-style summary
- `tool.py`: terminal tool schema example

Run:

```bash
snowl eval examples/terminalbench-official/project.yml
```

Benchmark mode:

```bash
snowl bench run terminalbench --project examples/terminalbench-official/project.yml --split test
```

Settings live in `project.yml` under `benchmarks.terminalbench`, for example:

- `compose_build`
- `run_tests`
- `max_episodes`
- `max_parse_retries`
- `temperature`

Snowl isolates container trial names, compose resources, and log paths by `variant_id`, so multi-model TerminalBench runs do not collide.
