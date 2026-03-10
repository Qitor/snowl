# osworld-official

Official OSWorld example using Snowl's project-level model matrix authoring.

- `task.py`: loads OSWorld tasks from `references/OSWorld/evaluation_examples`
- `agent.py`: builds one OSWorld agent per declared model
- `scorer.py`: OSWorld benchmark scorer
- `tool.py`: built-in GUI tool contracts

## Model authoring

`model.yml` declares one provider and a tested model matrix:

```yaml
provider:
  kind: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: gpt4o_mini
      model: gpt-4o-mini
    - id: qwen3_8b
      model: Qwen/Qwen3-8B
```

The OSWorld agent receives explicit model config per variant. It no longer relies on process-global `OPENAI_MODEL` to decide which tested model to run.

## Run

```bash
snowl eval examples/osworld-official
```

Benchmark mode:

```bash
snowl bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1
```

Optional runtime knobs:

```bash
export SNOWL_OSWORLD_MAX_STEPS=15
export SNOWL_OSWORLD_TEMPERATURE=0.2
export SNOWL_OSWORLD_SAMPLE_LIMIT=1
export SNOWL_OSWORLD_RECORDING=1
export SNOWL_OSWORLD_OBSERVE_ACCESSIBILITY=0
export SNOWL_OSWORLD_OBSERVE_TERMINAL=0
```

Notes:

- Snowl auto-prepares the OSWorld VM disk on first run and caches it under `references/OSWorld/docker_vm_data`
- Snowl adds required container capability by default (`--cap-add NET_ADMIN`) for OSWorld networking and port forwarding
- trial-level recordings and saved observation frames are variant-scoped, so multi-model runs do not overwrite each other
- first run may take a long time; check `run.log` for progress

## Evaluator dependencies

```bash
pip install -e \".[osworld_eval]\"
python -m playwright install chromium
```

Or the benchmark-scoped minimal dependency set:

```bash
pip install -r snowl/benchmarks/osworld/requirements-eval-min.txt
python -m playwright install chromium
```
