# agentsafetybench-official

Official-style Agent-SafetyBench example with Snowl primitives:

- `task.py`: load Agent-SafetyBench cases from `references/Agent-SafetyBench/data/released_data.json`.
- `agent.py`: run the official agent-environment interaction loop via Python API.
- `scorer.py`: run the official Shield-based safety scorer.

## Setup

Install Agent-SafetyBench dependencies first:

```bash
cd references/Agent-SafetyBench
pip install -r requirements.txt
```

Install those packages into the same Python environment that provides the `snowl` command.

Agent-SafetyBench uses the newer OpenAI Python SDK interface (`from openai import OpenAI`), so the runtime environment must have `openai>=1.0.0`.

## Run

Configure the evaluated agent model in `agent.py`, or by env:

```bash
export SNOWL_AGENTSAFETYBENCH_MODEL="gpt-4o-mini"
export SNOWL_AGENTSAFETYBENCH_API_KEY="YOUR_KEY"
export SNOWL_AGENTSAFETYBENCH_BASE_URL="https://openrouter.ai/api/v1"
```

Configure the Shield scorer model path:

```bash
export SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_PATH="/path/to/ShieldAgent"
```

If you do not provide `SNOWL_AGENTSAFETYBENCH_SHIELD_MODEL_PATH`, Snowl uses the official model id `thu-coai/ShieldAgent`.
If the model is not already cached locally, `transformers` will download it the first time scoring runs.

Run from the Snowl repo root:

```bash
export SNOWL_AGENTSAFETYBENCH_LIMIT=3  # recommended for the first smoke test
snowl eval examples/agentsafetybench-official
```

Outputs:

```text
examples/agentsafetybench-official/outputs/run-<timestamp>/
├── trajectories/
│   └── <sample_id>.json
├── scores/
│   └── <sample_id>.json
├── trajectories.jsonl
└── scores.jsonl
```

Optional:

```bash
export SNOWL_AGENTSAFETYBENCH_LIMIT=20
export SNOWL_AGENTSAFETYBENCH_MAX_ROUNDS=10
export SNOWL_AGENTSAFETYBENCH_OUTPUT_DIR="/absolute/path/to/output_dir"
```

The defaults in `agent.py` and `scorer.py` can also be edited directly if you prefer to keep model name, base URL, API key, or Shield model path in code.

Common failure mode:

- If all samples fail immediately and `run.log` contains `cannot import name 'OpenAI' from 'openai'`, the `snowl` environment is still using an old `openai` package. Upgrade it inside the same environment that runs `snowl`.
