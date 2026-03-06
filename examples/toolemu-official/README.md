# toolemu-official

Official-style ToolEmu example with Snowl primitives:

- `task.py`: load ToolEmu cases from `references/ToolEmu/assets/all_cases.json`.
- `agent.py`: run ToolEmu native executor via Python API (`build_agent_executor`).
- `scorer.py`: run ToolEmu native evaluators via Python API (`agent_safe` + `agent_help`).

## Setup

ToolEmu itself has extra Python dependencies and also requires PromptCoder.
Before running this Snowl example, install them following the ToolEmu README:

```bash
# Clone the repositories
git clone https://github.com/ryoungj/ToolEmu.git
git clone https://github.com/dhh1995/PromptCoder.git

# Install the packages
cd PromptCoder
pip install -e .
cd ../ToolEmu
pip install -e .  # ToolEmu expects openai==0.28.1
```

Install Snowl and ToolEmu into the same Python environment. If `snowl` is installed in a dedicated conda or venv, use that environment's `pip`.

## Run

Set env:

```bash
export SNOWL_TOOLEMU_AGENT_MODEL="gpt-3.5-turbo"
export SNOWL_TOOLEMU_SIMULATOR_MODEL="gpt-3.5-turbo"
export SNOWL_TOOLEMU_EVALUATOR_MODEL="gpt-3.5-turbo"
export SNOWL_TOOLEMU_AGENT_API_KEY="..."
export SNOWL_TOOLEMU_SIMULATOR_API_KEY="..."
export SNOWL_TOOLEMU_EVALUATOR_API_KEY="..."
```

Run:

```bash
cd /path/to/snowl
snowl eval examples/toolemu-official
```

Outputs:

```text
examples/toolemu-official/outputs/run-<timestamp>/
├── trajectories/
│   ├── <sample_id>.json
│   └── <sample_id>_simplified.txt
├── scores/
│   └── <sample_id>.json
├── trajectories.jsonl
└── scores.jsonl
```

Optional output override:

```bash
export SNOWL_TOOLEMU_OUTPUT_DIR="/absolute/path/to/output_dir"
```

Optional:

```bash
export SNOWL_TOOLEMU_SPLIT="official"
export SNOWL_TOOLEMU_LIMIT=5
export SNOWL_TOOLEMU_AGENT_TYPE="naive"             # naive|ss_only|helpful_ss
export SNOWL_TOOLEMU_SIMULATOR_TYPE="adv_thought"   # adv_thought|std_thought|normal
export SNOWL_TOOLEMU_MAX_ITERATIONS=15
export SNOWL_TOOLEMU_AGENT_BASE_URL="https://api.openai.com/v1"
export SNOWL_TOOLEMU_SIMULATOR_BASE_URL="https://api.openai.com/v1"
export SNOWL_TOOLEMU_EVALUATOR_BASE_URL="https://api.openai.com/v1"
export SNOWL_TOOLEMU_AGENT_TIMEOUT=6000
export SNOWL_TOOLEMU_SIMULATOR_TIMEOUT=6000
export SNOWL_TOOLEMU_EVALUATOR_TIMEOUT=6000
```

The defaults in `agent.py` and `scorer.py` can also be edited directly if you prefer not to use environment variables.

Benchmark mode:

```bash
cd /path/to/snowl
snowl bench run toolemu --project examples/toolemu-official --split official
```

This implementation follows Snowl's benchmark contract:

- benchmark adapter loads ToolEmu cases into `Task`
- project-local `agent.py` defines the tested ToolEmu agent behavior
- project-local `scorer.py` uses ToolEmu's own evaluators

So the integration reuses ToolEmu's execution and scoring logic directly instead of re-implementing the benchmark in Snowl.
