# ToolEmu Emulation

Run LM-emulated tool execution for safety evaluation using the ToolEmu approach.

---

## Overview

ToolEmu's core innovation is LM-emulated tool execution: instead of running real
tools, an LM simulator generates realistic tool observations. This enables
safety evaluation of agents in virtual environments where real tool execution
would be costly or dangerous.

The emulation pipeline in Snowl:

1. **Stub tools** return a sentinel value `{"__emulated__": True}`
2. **EmulatedToolWrapper** (a ToolMiddleware) intercepts the sentinel in
   `intercept_result`
3. The wrapper calls an **emulator LM** to generate a realistic tool observation
4. Optionally, a **critiquer LM** reviews and revises the observation
5. The emulated observation replaces the sentinel and reaches the agent

---

## Quick setup

ToolEmu emulation uses assets from the ToolEmu reference repository. When the
official safety/helpfulness scorer is enabled, it also imports ToolEmu's
original evaluator prompts and parsers, which depend on PromptCoder's
`procoder` package.

```bash
git clone <TOOLEMU_GIT_URL> references/ToolEmu
git clone <PROMPTCODER_GIT_URL> references/PromptCoder
```

### 1. Create an example project

Use the built-in example:

```bash
snowl eval examples/toolemu-emulation/project.yml --limit 5
```

### 2. Or build your own

```python
# agent.py
from snowl.agents import ReActAgent, build_model_variants
from snowl.tools.emulated_tool import EmulatedToolWrapper, make_stub_tool
from snowl.benchmarks.toolemu.emulation import ToolEmuEmulator, load_toolkit_data

def _build_agent(model_entry, provider):
    client = OpenAICompatibleChatClient(model_entry.config)
    emulator_client = OpenAICompatibleChatClient(emulator_config)

    wrapper = EmulatedToolWrapper(
        emulator_client=emulator_client,
        simulator_type="adv_thought",
        tool_schemas=toolkit_schemas,
    )

    return ReActAgent(
        model_client=client,
        agent_id="toolemu_agent",
        middlewares=[wrapper],
        max_steps=10,
    )
```

---

## EmulatedToolWrapper configuration

```python
from snowl.tools.emulated_tool import EmulatedToolWrapper

wrapper = EmulatedToolWrapper(
    emulator_client=emulator_llm,       # LM that simulates tool observations
    critiquer_client=critiquer_llm,     # Optional LM that reviews observations
    simulator_type="std_thought",        # "std_thought" or "adv_thought"
    scheduler=scheduler,                 # Optional ResourceScheduler
    tool_schemas=tool_schemas,           # Dict mapping tool name to spec
    num_critique_steps=0,                # Number of critique rounds
    emit_fn=emit_fn,                     # Optional callback for trace events
    # Adversarial context (for adv_thought):
    underspecifications=...,
    risky_outcome=...,
    risky_actions=...,
    user_input=...,
    toolkit_descriptions=...,
)
```

### Simulator types

| Type | Description |
|------|-------------|
| `std_thought` | Generates realistic, accurate observations |
| `adv_thought` | Stress-tests the agent with challenging but realistic scenarios |

### Critique rounds

When `num_critique_steps > 0` and `critiquer_client` is set, the wrapper runs
critique rounds after the initial emulation. The critiquer reviews realism,
accuracy, and consistency, and may revise the observation.

---

## EmulationScratchpad

Tracks the action/observation trajectory across tool calls:

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

---

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
```

---

## Stub tools

`make_stub_tool` creates `ToolSpec` objects whose callables return the sentinel:

```python
from snowl.tools.emulated_tool import make_stub_tool

spec = make_stub_tool(
    name="SearchEmail",
    description="Search emails",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
```

---

## Scorer integration

The `ToolEmuScorer` looks for `toolemu.emulation` trace events. When found, it
extracts the trajectory and computes:

| Metric | Description |
|--------|-------------|
| `toolemu_toolcall_risk` | Risk assessment of individual tool calls |
| `toolemu_helpfulness` | How well the agent fulfilled the user's request |
| `toolemu_overall` | Combined risk/helpfulness score |

The example project enables the official ToolEmu evaluator path. In that mode,
Snowl reuses ToolEmu's original `AgentRiskyToolCallEvaluator` and
`AgentHelpfulnessEvaluator` prompt construction, `procoder`/PromptCoder
rendering, case preprocessing, and output parser. The actual judge model call is
sent through the evaluator LLM configured in the Snowl project YAML.

---

## Comparison with reference ToolEmu

| Aspect | Reference ToolEmu | Snowl Implementation |
|--------|-------------------|---------------------|
| Evaluator prompt system | procoder + LangChain | procoder/PromptCoder + Snowl `ChatModelClient` |
| Agent framework | LangChain AgentExecutor | ReActAgent with ToolMiddleware |
| Tool execution | Virtual agent executor class | EmulatedToolWrapper middleware |
| Critique | Multiple rounds with LLMChain | Multiple rounds with OpenAICompatibleChatClient |
| Concurrency | No built-in rate limiting | provider_admission via ResourceScheduler |
