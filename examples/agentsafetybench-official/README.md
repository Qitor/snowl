# agentsafetybench-official

Official-style Agent-SafetyBench example using Snowl's project-level model matrix authoring.

- `task.py`: loads cases from `references/Agent-SafetyBench/data/released_data.json`
- `agent.py`: builds one evaluated agent per `agent_matrix.models` entry
- `scorer.py`: uses the official Shield-based scorer

## Setup

Install Agent-SafetyBench dependencies into the same environment as `snowl`:

```bash
cd references/Agent-SafetyBench
pip install -r requirements.txt
```

## Model authoring

`model.yml` declares the tested agent sweep:

```yaml
provider:
  kind: openai_compatible
  base_url: https://openrouter.ai/api/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: gpt4o_mini
      model: gpt-4o-mini
    - id: qwen3_32b
      model: Qwen/Qwen3-32B
```

The scorer is not judge-LLM based here, so there is no `judge.model` requirement.

## Run

```bash
export SNOWL_AGENTSAFETYBENCH_LIMIT=3
export SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_PATH="/path/to/ShieldAgent"
snowl eval examples/agentsafetybench-official
```

Optional:

```bash
export SNOWL_AGENTSAFETYBENCH_LIMIT=20
export SNOWL_AGENTSAFETYBENCH_MAX_ROUNDS=10
export SNOWL_AGENTSAFETYBENCH_OUTPUT_DIR="/absolute/path/to/output_dir"
```

If you do not provide `SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_PATH`, Snowl uses `thu-coai/ShieldAgent`.
