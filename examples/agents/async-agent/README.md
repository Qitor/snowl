# Async Agent

This is the smallest native Snowl agent shape.

Required contract:

```python
agent_id = "stable-agent-id"

async def run(state, context, tools=None):
    ...
    return state
```

Use a stable `agent_id`; it becomes part of trial identity, retry keys, and run artifacts.
