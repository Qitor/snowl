# API Reference

Complete reference for Snowl's public Python API.

---

## Modules

| Module | Description |
|--------|-------------|
| [Core](core.md) | Task, Agent, Scorer protocols, data classes, decorators |
| [Agents](agents.md) | ReActAgent, ChatAgent, build_model_variants |
| [Model Client](model-client.md) | OpenAICompatibleChatClient, configuration |
| [Tools & Middleware](tools-middleware.md) | ToolMiddleware, MiddlewareChain, EmulatedToolWrapper |
| [Benchmarks](benchmarks.md) | Benchmark adapters, BaseBenchmarkAdapter, registry |
| [Scorers](scorers.md) | Built-in scorer primitives and composable scorers |
| [UI](ui.md) | Console renderers, UI events, panel configuration |

## Quick import reference

```python
# Core contracts
from snowl.core import Task, Agent, Scorer, AsyncScorer
from snowl.core import AgentState, AgentContext, Score, ScoreContext, TaskResult
from snowl.core import EnvSpec, ToolSpec, SandboxSpec
from snowl.core import StopReason, TaskStatus

# Decorators
from snowl.core import agent, task, scorer, tool

# Agents
from snowl.agents import ReActAgent, ChatAgent, build_model_variants

# Model client
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig

# Tool middleware
from snowl.tools.middleware import ToolMiddleware, MiddlewareChain, LoggingMiddleware

# Emulated tools
from snowl.tools.emulated_tool import EmulatedToolWrapper, make_stub_tool, EmulationScratchpad

# Scorers
from snowl.scorer import answer_match, function_call_match, tool_trace_policy
from snowl.scorer import state_transition, checkpoint_score, canary_leak
from snowl.scorer import regex_grade_judge, model_as_judge_json
from snowl.scorer import weighted, chain, choice_answer
```
