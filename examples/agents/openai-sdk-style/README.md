# OpenAI SDK Style Agent

Wrap your existing OpenAI SDK code behind Snowl's async `run(state, context, tools=None)` contract.

The example keeps the SDK client optional so the file can be imported without credentials. In a real project, construct `OpenAISDKStyleAgent(client=...)` in `agent.py` and keep `agent_id` stable across runs.
