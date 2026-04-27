# LangGraph Wrapper

This example adapts a LangGraph app to Snowl without changing benchmark code.

Instantiate the wrapper with your compiled graph:

```python
agent = LangGraphWrapperAgent(graph=compiled_graph)
```

Snowl passes messages through `state.messages` and task/sample context through `context`. Keep `agent_id` stable so dashboards and retries can compare the same agent over time.
