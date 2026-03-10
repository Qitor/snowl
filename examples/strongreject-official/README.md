# strongreject-official

Official StrongReject example using Snowl's project-level model matrix authoring.

- `task.py`: loads StrongReject prompts and wraps them with `AIM.txt`
- `agent.py`: uses `build_model_variants(...)` to expand one provider into multiple tested models
- `scorer.py`: uses `judge.model` from `model.yml` for the StrongReject judge

## Model authoring

`model.yml` is the source of truth:

```yaml
provider:
  kind: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: qwen25_7b
      model: Qwen/Qwen2.5-7B-Instruct
    - id: qwen3_32b
      model: Qwen/Qwen3-32B

judge:
  model: gpt-4o-mini
```

Rules:

- `agent_matrix.models` = tested agent models
- `judge.model` = scorer judge model
- these are intentionally separate

## Run

```bash
snowl eval examples/strongreject-official
```

Snowl will expand the project into `Task x AgentVariant x Sample`, so one run compares all declared models.
