# Safety Benchmark Smoke

This example shows how to run a tiny real-model smoke test for Snowl's
safety benchmark adapters:

- `xstest`
- `coconot`
- `fortress_adversarial`
- `fortress_benign`
- `agentharm`
- `agentharm_benign`

It is intentionally configured for small `--limit` runs. Use it to verify:

- remote model endpoints and credentials
- pinned benchmark asset download/cache
- judge regex parsing and Snowl aggregate artifacts

## Setup

Install optional dataset dependencies:

```bash
pip install -e '.[safety_assets]'
```

Set an API key. The example reads `SNOWL_SMOKE_API_KEY` first and then falls
back to `INF_API_KEY`.

```bash
export SNOWL_SMOKE_API_KEY="..."
```

The provided `project.yml` demonstrates three SII/OpenAI-compatible endpoints
that were useful during development. Replace `agent_matrix.models[*].model` and
`metadata.base_url` with your own OpenAI-compatible model endpoints as needed.

The judge defaults to:

```bash
SNOWL_SMOKE_JUDGE_MODEL=deepseek-v3-ep
SNOWL_SMOKE_JUDGE_BASE_URL=http://dsv3.sii.edu.cn/v1
```

Override them for your environment:

```bash
export SNOWL_SMOKE_JUDGE_MODEL="your-judge-model"
export SNOWL_SMOKE_JUDGE_BASE_URL="https://your-endpoint/v1"
```

## Run Smoke Checks

Run the default Coconot smoke:

```bash
snowl bench run coconot \
  --project examples/safety-benchmark-smoke \
  --split test \
  --limit 1 \
  --max-running-trials 1 \
  --max-scoring-tasks 1 \
  --provider-budget remote-smoke=1
```

Try XSTest safe and unsafe subsets:

```bash
snowl bench run xstest \
  --project examples/safety-benchmark-smoke \
  --split test \
  --limit 1 \
  --adapter-arg subset=safe

snowl bench run xstest \
  --project examples/safety-benchmark-smoke \
  --split test \
  --limit 1 \
  --adapter-arg subset=unsafe
```

Try FORTRESS:

```bash
snowl bench run fortress_benign \
  --project examples/safety-benchmark-smoke \
  --split train \
  --limit 1
```

For adversarial FORTRESS, you may provide multiple comma-separated judges:

```bash
export SNOWL_SMOKE_JUDGE_MODELS="judge-a,judge-b,judge-c"

snowl bench run fortress_adversarial \
  --project examples/safety-benchmark-smoke \
  --split train \
  --limit 1
```

AgentHarm can be loaded with this project, but samples may request tools via
`target_functions`. Add a `tool.py` with matching Snowl tools before running
tool-requiring samples.
