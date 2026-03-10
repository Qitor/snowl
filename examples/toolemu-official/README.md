# toolemu-official

Official-style ToolEmu example using Snowl's project-level model matrix authoring.

- `task.py`: loads ToolEmu cases from `references/ToolEmu/assets/all_cases.json`
- `agent.py`: builds one tested ToolEmu agent per `agent_matrix.models` entry
- `scorer.py`: uses `judge.model` as the evaluator/support model

## Setup

Install ToolEmu and PromptCoder into the same environment as `snowl`:

```bash
git clone https://github.com/ryoungj/ToolEmu.git
git clone https://github.com/dhh1995/PromptCoder.git

cd PromptCoder
pip install -e .
cd ../ToolEmu
pip install -e .
```

## Model authoring

`model.yml` declares:

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
    - id: qwen3_32b
      model: Qwen/Qwen3-32B

judge:
  model: gpt-4.1-mini
```

Semantics:

- `agent_matrix.models` = tested ToolEmu agent models
- `judge.model` = shared support model for simulator/evaluator roles

## Run

```bash
snowl eval examples/toolemu-official
```

Benchmark mode:

```bash
snowl bench run toolemu --project examples/toolemu-official --split official
```

Optional runtime knobs:

```bash
export SNOWL_TOOLEMU_SPLIT="official"
export SNOWL_TOOLEMU_LIMIT=5
export SNOWL_TOOLEMU_AGENT_TYPE="naive"
export SNOWL_TOOLEMU_SIMULATOR_TYPE="adv_thought"
export SNOWL_TOOLEMU_MAX_ITERATIONS=15
export SNOWL_TOOLEMU_OUTPUT_DIR="/absolute/path/to/output_dir"
```
