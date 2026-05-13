# Multi-Model Sweeps

Evaluate multiple models side by side by adding them to `agent_matrix.models`.

---

## Basic setup

Add multiple models to `project.yml`:

```yaml
agent_matrix:
  models:
    - id: glm51
      model: glm-5.1-w4a8
      metadata:
        company: zhipu
        source_type: open_source
    - id: qwen3
      model: Qwen/Qwen3-32B
      metadata:
        company: alibaba
        source_type: open_source
    - id: gpt4o
      model: gpt-4o-2024-05-13
      metadata:
        company: openai
        source_type: proprietary
```

Snowl creates a trial for every (task × model × sample) combination. Results
are aggregated with ranked metric values in the Compare panel.

---

## Per-model provider overrides

Each model can use a different provider:

```yaml
provider:
  id: default
  kind: openai_compatible
  base_url: https://api.default.com/v1
  api_key: sk-default

agent_matrix:
  models:
    - id: model_a
      model: model-a-v1
    - id: model_b
      model: model-b-v1
      provider:                # Override provider for this model
        base_url: https://api.other.com/v1
        api_key: sk-other
```

---

## Model metadata

The `metadata` field is optional but recommended for analysis and dashboard
display:

```yaml
models:
  - id: my_model
    model: my-model-v1
    metadata:
      company: acme
      source_type: open_source   # open_source, proprietary, hybrid
      size: 32B                  # Model size (informal)
      license: apache-2.0        # License identifier
```

Metadata is carried into run artifacts and can be used for grouped metrics.

---

## Running sweeps

```bash
# Run all model variants
snowl eval ./project.yml

# Limit samples for quick comparison
snowl eval ./project.yml --limit 10

# Adjust concurrency
snowl eval ./project.yml --max-running-trials 8
```

---

## Comparing results

After a run, use the compare tools:

```bash
# Compare two runs
snowl compare run_a run_b

# Generate HTML report
snowl report latest --format html

# Rescore with a different scorer
snowl rescore latest --scorer my_scorer
```

The aggregate metrics in `.snowl/runs/<run_id>/aggregate.json` are keyed by
(task, agent, variant), making it straightforward to compare models.

---

## Provider budgets

When evaluating multiple models that share a provider, use provider budgets to
avoid rate limiting:

```yaml
runtime:
  provider_budgets:
    default: 8          # Max 8 concurrent calls to default provider
    openai: 4           # Max 4 concurrent calls to OpenAI
```

Or via CLI:

```bash
snowl eval ./project.yml --provider-budget default=8 --provider-budget openai=4
```
