# ToolEmu LM Emulation

ToolEmu's core innovation is LM-emulated tool execution: instead of running real tools, an LM simulator generates realistic tool observations. This enables safety evaluation of agents in virtual environments where real tool execution would be costly or dangerous.

## Architecture

The emulation pipeline in Snowl:

1. **Stub tools** return a sentinel value `{"__emulated__": True}`
2. **EmulatedToolWrapper** (a ToolMiddleware) intercepts the sentinel in `intercept_result`
3. The wrapper calls an **emulator LM** to generate a realistic tool observation
4. Optionally, a **critiquer LM** reviews and revises the observation
5. The emulated observation replaces the sentinel and reaches the agent

```
Agent makes tool call
  → MiddlewareChain.intercept_call (passthrough)
  → Stub tool returns {"__emulated__": True}
  → MiddlewareChain.intercept_result
  → EmulatedToolWrapper.emulate_tool_call()
    → Build emulator prompt (system + user)
    → Call emulator LM (with provider_admission)
    → Parse observation from response
    → Optional critique rounds
    → Update scratchpad
    → Emit toolemu.emulation trace event
  → Emulated observation returned to agent
```

## EmulationScratchpad

Tracks the action/observation trajectory across tool calls within a single agent run:

```python
from snowl.tools.emulated_tool import EmulationScratchpad

scratchpad = EmulationScratchpad()
scratchpad.add(
    action="SearchEmail",
    action_input='{"query": "meeting"}',
    observation='{"emails": [{"id": "e1", "subject": "Team Meeting"}]}',
    thought_summary="Found meeting emails.",
)
print(scratchpad.render())
```

Output:
```
Action: SearchEmail
Action Input: {"query": "meeting"}

Simulator Log Summary: Found meeting emails.
Observation: {"emails": [{"id": "e1", "subject": "Team Meeting"}]}
```

## EmulatedToolWrapper

### Configuration

```python
from snowl.tools.emulated_tool import EmulatedToolWrapper

wrapper = EmulatedToolWrapper(
    emulator_client=emulator_llm,       # LM that simulates tool observations
    critiquer_client=critiquer_llm,     # Optional LM that reviews observations
    simulator_type="std_thought",        # "std_thought" or "adv_thought"
    scheduler=scheduler,                 # Optional ResourceScheduler for provider_admission
    tool_schemas=tool_schemas,           # Dict mapping tool name to tool spec dict
    num_critique_steps=0,                # Number of critique rounds
    emit_fn=emit_fn,                     # Optional callback for trace events
    # Adversarial context (set per-run for adv_thought):
    underspecifications=...,
    risky_outcome=...,
    risky_actions=...,
    user_input=...,
    toolkit_descriptions=...,
)
```

### Simulator Types

- **`std_thought`**: Standard simulator that generates realistic, accurate observations
- **`adv_thought`**: Adversarial simulator that stress-tests the agent by crafting challenging scenarios while maintaining realism

### Sentinel Mechanism

Stub tools return `{"__emulated__": True}`. The wrapper's `intercept_result` detects this sentinel and replaces it with the emulated observation. Non-sentinel results pass through unchanged.

### Critique Rounds

When `num_critique_steps > 0` and `critiquer_client` is set, the wrapper runs critique rounds after the initial emulation. The critiquer reviews realism, accuracy, and consistency, and may revise the observation.

### Trace Events

The wrapper emits `toolemu.emulation` trace events (if `emit_fn` is provided) containing:
- `tool_name`, `tool_args`, `observation`, `thought_summary`
- `simulator_type`, `scratchpad_entries` count

## Prompt Templates

The emulator prompts are ported from the original ToolEmu procoder templates to plain f-string format:

- **Standard**: `STD_SIMULATOR_SYSTEM_PROMPT` + `STD_SIMULATOR_USER_PROMPT`
- **Adversarial**: `ADV_SIMULATOR_SYSTEM_PROMPT` + `ADV_SIMULATOR_USER_PROMPT`
- **Critique**: `STD_CRITIQUE_PROMPT`, `ADV_CRITIQUE_PROMPT`, and repeat variants

Template variables: `{current_tool}`, `{current_tool_description}`, `{toolkit_descriptions}`, `{input}`, `{simulator_scratchpad}`, `{underspecifications}`, `{risky_outcome}`, `{risky_actions}` (adversarial only).

## ToolEmuEmulator

High-level orchestrator that wires everything together:

```python
from snowl.benchmarks.toolemu.emulation import ToolEmuEmulator, load_toolkit_data

toolkit_data = load_toolkit_data()  # Loads references/ToolEmu/assets/all_toolkits.json

emulator = ToolEmuEmulator(
    agent_llm=agent_client,
    emulator_llm=emulator_client,
    critiquer_llm=critiquer_client,  # Optional
    simulator_type="adv_thought",
    toolkit_data=toolkit_data,
    max_steps=10,
)

result_state = await emulator.run(sample, context)
# result_state.output["trace_events"] contains the toolemu.emulation event
```

## Stub Tools

`make_stub_tool` creates ToolSpec objects whose callables return the sentinel:

```python
from snowl.tools.emulated_tool import make_stub_tool

spec = make_stub_tool(
    name="SearchEmail",
    description="Search emails",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
```

## Scorer Integration

The `ToolEmuScorer` in `snowl/benchmarks/toolemu/scorer.py` looks for `toolemu.emulation` trace events. When found with a custom `evaluate_fn`, it extracts the trajectory and computes `toolemu_toolcall_risk`, `toolemu_helpfulness`, and `toolemu_overall` metrics.

## Comparison with Reference ToolEmu

| Aspect | Reference ToolEmu | Snowl Implementation |
|--------|-------------------|---------------------|
| Prompt system | procoder + LangChain | Plain f-string templates + OpenAICompatibleChatClient |
| Agent framework | LangChain AgentExecutor | ReActAgent with ToolMiddleware |
| Tool execution | Virtual agent executor class | EmulatedToolWrapper middleware |
| Observation format | Simulator Thought + Log Summary + Observation JSON | Same (parsed from LM response) |
| Critique | Multiple rounds with LLMChain | Multiple rounds with OpenAICompatibleChatClient |
| Concurrency | No built-in rate limiting | provider_admission via ResourceScheduler |
| Scratchpad | Managed in executor class | EmulationScratchpad dataclass |
