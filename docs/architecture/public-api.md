# Public API — Snowl

> Audited 2026-05-18. Lists the currently intended public APIs exported from
> `snowl` and `snowl.core`. Anything not listed here is internal and may change
> without notice.

---

## Package `snowl` (top-level facade)

These names are re-exported from `snowl/__init__.py` and constitute the primary
user-facing import surface.

### Version

| Name | Type | Stability |
|------|------|-----------|
| `__version__` | `str` | Stable |

### Core contracts (re-exported from `snowl.core`)

| Name | Type | Stability |
|------|------|-----------|
| `Task` | dataclass | Stable |
| `TaskProvider` | Protocol | Stable |
| `task` | decorator | Stable |
| `Agent` | Protocol | Stable |
| `AgentState` | dataclass | Stable |
| `AgentContext` | dataclass | Stable |
| `Action` | dataclass | Stable |
| `Observation` | dataclass | Stable |
| `StopReason` | enum | Stable |
| `AgentVariant` | dataclass | Stable |
| `AgentVariantAdapter` | dataclass | Stable |
| `Scorer` | Protocol | Stable |
| `AsyncScorer` | Protocol | Stable |
| `Score` | dataclass | Stable |
| `ScoreContext` | dataclass | Stable |
| `TaskResult` | dataclass | Stable |
| `TaskStatus` | enum | Stable |
| `Timing` | dataclass | Stable |
| `Usage` | dataclass | Stable |
| `ErrorInfo` | dataclass | Stable |
| `ArtifactRef` | dataclass | Stable |
| `EnvSpec` | dataclass | Stable |
| `SandboxSpec` | dataclass | Stable |
| `FileOps` | dataclass | Stable |
| `ProcessOps` | dataclass | Stable |
| `WebOps` | dataclass | Stable |
| `ToolSpec` | dataclass | Stable |
| `ToolRegistry` | class | Stable |
| `tool` | decorator | Stable |

### Agents

| Name | Type | Stability |
|------|------|-----------|
| `ChatAgent` | dataclass | Stable |
| `ReActAgent` | dataclass | Stable |

### Model

| Name | Type | Stability |
|------|------|-----------|
| `OpenAICompatibleChatClient` | class | Stable |
| `OpenAICompatibleConfig` | dataclass | Stable |
| `load_openai_compatible_config` | function | Stable |

### Scorers

| Name | Type | Stability |
|------|------|-----------|
| `includes` | function | Stable |
| `match` | function | Stable |
| `pattern` | function | Stable |
| `model_as_judge_json` | function | Stable |

### Runtime

| Name | Type | Stability |
|------|------|-----------|
| `TrialRequest` | dataclass | Stable |
| `TrialOutcome` | dataclass | Stable |
| `TrialLimits` | dataclass | Stable |
| `execute_trial` | function | Stable |

### Environments

| Name | Type | Stability |
|------|------|-----------|
| `LocalEnv` | class | Stable |
| `LocalSandboxRuntime` | class | Stable |

### Errors

| Name | Type | Stability |
|------|------|-----------|
| `SnowlValidationError` | exception | Stable |

---

## Package `snowl.core` (core contracts)

These names are exported from `snowl/core/__init__.py` and represent the
framework-independent contract layer.

### Agent contracts (`snowl.core.agent`)

| Name | Type | Notes |
|------|------|-------|
| `Agent` | Protocol | `agent_id: str`, `async def run(state, context, tools=None) -> AgentState` |
| `AgentState` | dataclass | Mutable agent execution state |
| `AgentContext` | dataclass | Immutable context passed to agents |
| `Action` | dataclass | A tool call or final answer |
| `Observation` | dataclass | Result from a tool execution |
| `StopReason` | StrEnum | COMPLETED, MAX_STEPS, ERROR, TOOL_ERROR |
| `agent` | decorator | Stamps metadata via `declare()` |
| `validate_agent` | function | Runtime contract check |

### Agent variant contracts (`snowl.core.agent_variant`)

| Name | Type | Notes |
|------|------|-------|
| `AgentVariant` | dataclass | Binds agent + execution_mode + variant_id + model |
| `AgentVariantAdapter` | dataclass | Wraps Agent with variant metadata |
| `bind_agent_variant` | function | Create AgentVariantAdapter |
| `make_agent_variant` | function | Construct AgentVariant |
| `validate_agent_variant` | function | Runtime contract check |

### Task contracts (`snowl.core.task`)

| Name | Type | Notes |
|------|------|-------|
| `Task` | dataclass | task_id, env_spec, sample_iter_factory, metadata |
| `TaskProvider` | Protocol | `def tasks() -> list[Task]` |
| `task` | decorator | Stamps metadata via `declare()` |
| `validate_task` | function | Runtime contract check |
| `validate_task_provider` | function | Runtime contract check |

### Scorer contracts (`snowl.core.scorer`)

| Name | Type | Notes |
|------|------|-------|
| `Scorer` | Protocol | `def score(task_result, trace, context) -> dict[str, Score]` |
| `AsyncScorer` | Protocol | `async def score(...) -> dict[str, Score]` |
| `Score` | dataclass | value (float), explanation (str), metadata |
| `ScoreContext` | dataclass | task_metadata, run_metadata |
| `SyncScorerAdapter` | class | Wraps sync Scorer as AsyncScorer |
| `is_async_scorer` | function | Duck-type check |
| `scorer` | decorator | Stamps metadata |
| `validate_scorer` | function | Runtime contract check |
| `validate_async_scorer` | function | Runtime contract check |
| `validate_scores` | function | Validate score dict |

### Task result contracts (`snowl.core.task_result`)

| Name | Type | Notes |
|------|------|-------|
| `TaskResult` | dataclass | task_id, agent_id, variant_id, status, scores, output, usage, timing |
| `TaskStatus` | StrEnum | SUCCESS, PARTIAL, ERROR, SKIPPED |
| `Timing` | dataclass | start_time, end_time, wall_seconds |
| `Usage` | dataclass | input_tokens, output_tokens, total_tokens |
| `ErrorInfo` | dataclass | error_type, message, traceback |
| `ArtifactRef` | dataclass | name, path, artifact_type |
| `validate_task_result` | function | Runtime contract check |

### Environment contracts (`snowl.core.env`)

| Name | Type | Notes |
|------|------|-------|
| `EnvSpec` | dataclass | env_type, provided_ops, sandbox_spec |
| `SandboxSpec` | dataclass | image, dockerfile, build_context, provider |
| `FileOps` | dataclass | Filesystem operation capabilities |
| `ProcessOps` | dataclass | Process execution capabilities |
| `WebOps` | dataclass | Web/browser capabilities |
| `ensure_tool_ops_compatible` | function | Compatibility check |
| `validate_env_spec` | function | Runtime contract check |

### Tool contracts (`snowl.core.tool`)

| Name | Type | Notes |
|------|------|-------|
| `ToolSpec` | dataclass | name, description, parameters, required |
| `ToolRegistry` | class | Registry of named ToolSpec instances |
| `build_tool_spec` | function | Build ToolSpec from function or dict |
| `get_default_tool_registry` | function | Global default registry |
| `resolve_tool_spec` | function | Resolve spec from registry or inline |
| `tool` | decorator | Register tool spec |

### Declaration system (`snowl.core.declarations`)

| Name | Type | Notes |
|------|------|-------|
| `declare` | function | Stamp metadata onto callables |
| `DeclarationMeta` | dataclass | Metadata container |

---

## Package `snowl.model.base` (model provider protocol)

| Name | Type | Stability |
|------|------|-----------|
| `ChatModelClient` | Protocol | Stable — the protocol agents should depend on |

Methods: `generate(messages, tools=None, **kwargs)`, `generate_stream(messages, tools=None, **kwargs)`

---

## Package `snowl.tools.middleware` (tool middleware)

| Name | Type | Stability |
|------|------|-----------|
| `ToolMiddleware` | Protocol | Experimental |
| `MiddlewareChain` | class | Experimental |
| `LoggingMiddleware` | class | Experimental |
| `IdentityMiddleware` | class | Experimental |

---

## Internal APIs (not stable)

The following modules are internal implementation details. Their APIs may change
without notice between versions:

- `snowl.dispatch` — trial scheduling and orchestration
- `snowl.eval_loop` — single-trial lifecycle
- `snowl.eval_spec` — normalized run inputs
- `snowl.planning` — trial planning
- `snowl.artifacts` — artifact persistence
- `snowl.observability.events` — event bus
- `snowl.runtime.engine` — trial execution engine
- `snowl.runtime.policy` — runtime budget policy
- `snowl.runtime.resource_scheduler` — concurrency control
- `snowl.runtime.recovery` — retry management
- `snowl.runtime.container_providers` — container lifecycle
- `snowl.runtime.container_contract` — container specs
- `snowl.benchmarks.registry` — benchmark registry
- `snowl.benchmarks.base_adapter` — adapter template
- `snowl.web.monitor` — SQLite run index
- `snowl.ui.contracts` — UI event contracts
