# toolemu-official

Snowl-native ToolEmu example using YAML-first multi-model authoring.

Files:

- `project.yml`: provider, tested models, eval code paths, runtime budgets, toolemu settings
- `task.py`: loads ToolEmu case data
- `agent.py`: builds one Snowl-native agent per model entry
- `scorer.py`: scores with Snowl's built-in trace-policy and helpfulness heuristics

Setup:

Provide a ToolEmu-style `all_cases.json` file through the adapter's `dataset_path`
or keep static case data under the configured project path.

Run:

```bash
snowl eval examples/toolemu-official/project.yml
```

Benchmark mode:

```bash
snowl bench run toolemu --project examples/toolemu-official/project.yml --split official
```

Settings live in `project.yml` under `benchmarks.toolemu`, for example:

- `output_dir`
- `run_stamp`

`agent_matrix.models` are the tested models.
