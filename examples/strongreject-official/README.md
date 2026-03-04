# strongreject-official

Official-style StrongReject example with Snowl primitives:

- `task.py`: load StrongReject tasks from CSV and wrap each prompt with `AIM.txt`.
- `agent.py`: auto-register multiple `ChatAgent` variants for multi-model comparison.
- `scorer.py`: benchmark-specific StrongReject scorer (judge model + formula).

## Run

Set env:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="..."
export SNOWL_AGENT_MODELS="gpt-4o-mini,qwen2.5-72b-instruct"
export OPENAI_MODEL="gpt-4o-mini"   # judge model for scorer
```

Run:

```bash
snowl eval examples/strongreject-official
```

Because `agent.py` exposes multiple agents, Snowl auto-expands to `1 Task x M Agents`
and shows model comparison results in one run.
