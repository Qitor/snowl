# osworld-official

Official OSWorld example using Snowl's YAML-first multi-model authoring.

Files:

- `project.yml`: provider, tested models, eval code paths, runtime budgets, osworld settings
- `task.py`: loads OSWorld tasks from `references/OSWorld/evaluation_examples`
- `agent.py`: builds one OSWorld agent per declared model
- `scorer.py`: OSWorld benchmark scorer
- `tool.py`: built-in GUI tool contracts

Run:

```bash
snowl eval examples/osworld-official/project.yml
```

Benchmark mode:

```bash
snowl bench run osworld --project examples/osworld-official/project.yml --split test --limit 1
```

Settings live in `project.yml` under `benchmarks.osworld`, for example:

- `max_steps`
- `temperature`
- `observation_type`
- `recording`
- `save_observation_frames`
- `ready_timeout`
- `image`
- `cap_add`
- `recordings_dir`

Notes:

- the agent receives explicit model config per variant
- trial-level recordings and observation frames are variant-scoped
- first run may take a long time while the VM image is prepared; check `run.log` for progress

Evaluator dependencies:

```bash
pip install -e ".[osworld_eval]"
python -m playwright install chromium
```
