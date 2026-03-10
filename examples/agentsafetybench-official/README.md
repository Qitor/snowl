# agentsafetybench-official

Official-style Agent-SafetyBench example using Snowl's YAML-first multi-model authoring.

Files:

- `project.yml`: provider, tested models, eval code paths, runtime budgets, agentsafetybench settings
- `task.py`: loads cases from `references/Agent-SafetyBench/data/released_data.json`
- `agent.py`: builds one evaluated agent per model entry
- `scorer.py`: uses the official Shield-based scorer

Setup:

```bash
cd references/Agent-SafetyBench
pip install -r requirements.txt
```

Run:

```bash
snowl eval examples/agentsafetybench-official/project.yml
```

Settings live in `project.yml` under `benchmarks.agentsafetybench`, for example:

- `temperature`
- `max_tokens`
- `max_rounds`
- `allow_empty`
- `shield_model_path`
- `shield_model_base`
- `shield_batch_size`

This benchmark does not require `judge.model`; the Shield-based scorer is configured entirely from YAML.
