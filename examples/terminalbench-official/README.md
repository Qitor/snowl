# terminalbench-official

Official-style Terminal-Bench example with Snowl primitives:

- `task.py`: loads tasks from `references/terminal-bench/original-tasks`.
- `agent.py`: Terminus-style command-batch loop over an OpenAI-compatible model.
- `scorer.py`: terminalbench scorer (pytest summary parse).
- `tool.py`: terminal tool schema example.

## Run

Set env:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-4o-mini"
```

Run:

```bash
snowl eval examples/terminalbench-official
```

Optional:

```bash
export SNOWL_TB_RUN_TESTS=1
```

When enabled, the agent attempts to execute each task's `run-tests.sh` and the scorer
uses pytest summary signals from output/trace.

