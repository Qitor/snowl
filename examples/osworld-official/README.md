# osworld-official

Official-style OSWorld example with Snowl primitives:

- `task.py`: load OSWorld tasks from `references/OSWorld/evaluation_examples`.
- `agent.py`: ReAct agent over OpenAI-compatible model.
- `scorer.py`: OSWorld benchmark scorer.
- `tool.py`: built-in GUI tool contracts.

## Run

Set env:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-4o-mini"
```

Run:

```bash
snowl eval examples/osworld-official
```

Optional:

```bash
export SNOWL_OSWORLD_MAX_STEPS=15
export SNOWL_OSWORLD_TEMPERATURE=0.2
```

