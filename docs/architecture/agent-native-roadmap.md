# Agent-Native Roadmap — Snowl

> Design document for the next 2-3 implementation rounds. This is a practical
> plan, not marketing copy. It covers what needs to be built, how it connects
> to the current architecture, and what trade-offs are involved.

---

## 1. Agent Adapter SDK

### Target interface

The Agent Adapter SDK should let framework authors wrap any agent framework
into Snowl's evaluation surface with minimal glue code. The core `Agent`
protocol already exists:

```python
class Agent:
    agent_id: str
    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState
```

The SDK should provide framework-specific wrappers that:
- Handle framework lifecycle (init, step loop, cleanup)
- Normalize framework output into Snowl's `AgentState.output` format
- Preserve framework-native traces alongside Snowl artifacts

### Framework support strategy

**OpenAI Agents SDK style agents**

OpenAI Agents SDK uses a `Runner` loop with tool calls, handoffs, and guardrails.
The wrapper should:
- Accept an OpenAI `Agent` definition and `Runner` config
- Map tool calls → Snowl `Action`, tool results → Snowl `Observation`
- Map handoffs as trace events
- Preserve the raw OpenAI response objects in `AgentState.output.raw_trace`

**LangGraph**

LangGraph agents are state machines with nodes (functions) and edges (transitions).
The wrapper should:
- Accept a compiled `CompiledGraph`
- Step through the graph, mapping each node invocation to a trace event
- Map tool calls/results using LangGraph's tool node conventions
- Preserve graph state snapshots in trace artifacts

**LangChain**

LangChain agents use a chain/executor pattern with tool calls.
The wrapper should:
- Accept a LangChain `AgentExecutor` or `Runnable`
- Map intermediate steps to trace events
- Map tool calls/results from LangChain's `AgentAction`/`AgentFinish`

**AutoGen/CrewAI-like multi-agent systems**

Multi-agent systems require special handling:
- Map each agent as a separate `agent_id` in the trace
- Use conversation turn events to capture inter-agent communication
- Optionally model the team as a single Snowl `Agent` that orchestrates internally

**QitOS**

QitOS agents use a specific task execution model.
The wrapper should:
- Accept QitOS agent configuration
- Map QitOS-specific tool definitions to Snowl `ToolSpec`
- Map QitOS state transitions to trace events

**Custom async Python agents**

The current `Agent` protocol already supports this directly. The SDK should
provide:
- A `BaseAgentAdapter` class with common utilities (timing, usage tracking, error handling)
- Example implementations for common patterns

### Normalization targets

The SDK must normalize these across all frameworks:

| Concept | Snowl representation |
|---------|---------------------|
| Messages (input/output) | `AgentState.output["message"]` with `role`/`content` |
| Tool calls | `Action` with `tool_name`, `tool_input` |
| Tool results | `Observation` with `tool_output`, `success` |
| State transitions | Trace events in `AgentState.output["trace_events"]` |
| Errors | `AgentState.stop_reason = StopReason.ERROR` + `ErrorInfo` |
| Token usage | `AgentState.output["usage"]` with `input_tokens`/`output_tokens` |
| Cost | `AgentState.output["cost"]` (optional) |
| Stop reasons | `StopReason` enum: COMPLETED, MAX_STEPS, ERROR, TOOL_ERROR |
| Raw traces | `AgentState.output["raw_trace"]` — framework-native trace data |

### Trace preservation

Each adapter must preserve the framework-native trace alongside the normalized
Snowl trace. This enables:
- Framework-specific debugging without losing information
- Cross-framework comparison using normalized fields
- Audit trails that capture what actually happened

Implementation: `AgentState.output["raw_trace"]` stores the framework-native
trace object (serialized to JSON-serializable form). `AgentState.output["trace_events"]`
stores the normalized Snowl trace.

---

## 2. Environment Blueprint System

### Concept

An Environment Blueprint describes *what* an evaluation environment provides,
independent of *how* a specific benchmark launches it. Currently, environment
descriptions are scattered across `EnvSpec`, `SandboxSpec`, container providers,
and benchmark-specific config.

The blueprint system should centralize:

1. **Environment description** — what capabilities and resources are available
2. **Launcher contract** — how to start/stop an environment instance
3. **Observation contract** — what observations the environment provides

### Blueprint types

**Terminal tasks**
- Environment: container or local shell
- Capabilities: `process.run`, `terminal.exec`, `terminal.send_keys`, `terminal.capture`
- Observations: stdout, stderr, exit codes
- Current: `TerminalEnv`, `TerminalBenchProvider`

**Browser/web tasks**
- Environment: browser (headless or headed)
- Capabilities: `browser.navigate`, `browser.click`, `browser.type`, `browser.screenshot`
- Observations: page DOM, screenshots, network requests
- Current: Not fully implemented; OSWorld GUI env partially covers this

**GUI/desktop tasks**
- Environment: VNC-connected desktop container
- Capabilities: `desktop.click`, `desktop.type`, `desktop.screenshot`, `desktop.hotkey`
- Observations: screenshots, accessibility tree
- Current: `GuiEnv`, `OSWorldProvider`

**Local file/workspace tasks**
- Environment: local filesystem workspace
- Capabilities: `file.read`, `file.write`, `file.list`, `process.run`
- Observations: file diffs, command outputs
- Current: `LocalEnv`, `RuntimeWorkspace`

**Tool/API simulation tasks**
- Environment: simulated tool endpoints
- Capabilities: tool calls with emulated responses
- Observations: tool call traces, emulation scores
- Current: `EmulatedToolWrapper`, `StatefulToolExecutor`

**Container-backed tasks**
- Environment: Docker/Podman container with lifecycle management
- Capabilities: all of the above depending on container config
- Observations: container logs, exit codes, test results
- Current: `ComposeTerminalProvider`, `DockerContainerProvider`

**Future: Mobile/computer-use tasks**
- Environment: mobile device or computer-use interface
- Capabilities: touch, swipe, type, screenshot
- Observations: screen state, app state

### Design: separate description from launcher

```python
@dataclass
class EnvironmentBlueprint:
    """Describes what an environment provides, not how to launch it."""
    blueprint_id: str
    env_type: str  # "terminal", "gui", "browser", "local", "tool_sim", "container"
    capabilities: tuple[str, ...]  # e.g., ("process.run", "terminal.exec")
    observation_types: tuple[str, ...]  # e.g., ("stdout", "stderr", "exit_code")
    resource_requirements: dict[str, Any]  # cpu, memory, gpu, etc.
    launcher_config: dict[str, Any]  # opaque config passed to the launcher
```

Launchers implement:

```python
class EnvironmentLauncher(Protocol):
    launcher_id: str
    supported_blueprint_types: tuple[str, ...]

    async def prepare(self, blueprint: EnvironmentBlueprint, context: LaunchContext) -> EnvironmentSession
    async def close(self, session: EnvironmentSession) -> dict[str, Any] | None
```

This decouples benchmark-specific launchers from the runtime engine. The current
`container_providers.py` hardcoded imports become unnecessary — benchmarks register
their launchers, and the runtime resolves them by blueprint type.

---

## 3. Frontier AI Risk Evaluation Support

### Risk domain metadata schema

Each benchmark adapter should declare its risk domains:

```python
@dataclass
class RiskDomain:
    domain_id: str  # e.g., "prompt_injection", "cyber_capability"
    display_name: str
    description: str
    severity_levels: tuple[str, ...]  # e.g., ("low", "medium", "high", "critical")
    categories: tuple[str, ...]  # sub-categories within the domain
```

Benchmarks declare risk domains in their `BenchmarkInfo`:

```python
@dataclass
class BenchmarkInfo:
    name: str
    ...
    risk_domains: tuple[RiskDomain, ...] = ()
```

### Risk categories to support

| Category | Domain ID | Example benchmarks |
|----------|-----------|-------------------|
| Prompt injection | `prompt_injection` | AgentDojo, IPI Coding Agent, ToolEmu |
| Harmful tool use | `harmful_tool_use` | AgentHarm, ToolEmu, AgentSafetyBench |
| Cyber capability | `cyber_capability` | CyberMetric, SecQA, WMDP-cyber |
| Deception | `deception` | Custom, future benchmarks |
| Autonomy | `autonomy` | Custom, OSWorld (long-horizon tasks) |
| Self-replication-style behavior | `self_replication` | Custom, future benchmarks |
| Long-horizon goal pursuit | `long_horizon` | TerminalBench, OSWorld |
| CBRN/hazardous knowledge | `cbrn_hazardous` | WMDP-chem, WMDP-bio |
| Privacy/security boundary violation | `privacy_violation` | Custom, future benchmarks |
| Multi-agent collusion | `multi_agent_collusion` | Custom, future benchmarks |
| Over-refusal and unsafe compliance | `over_refusal` | XSTest, Coconot, FORTRESS |
| Unsafe compliance | `unsafe_compliance` | StrongReject, AgentHarm |

### Risk representation in artifacts

**Sample-level**: Each `SampleData` can carry `risk_domain`, `risk_category`, and
`risk_severity` metadata fields.

**Score-level**: Each `Score` can carry `risk_domain` in its metadata. Scorers
that evaluate risk should tag their outputs.

**Run-level**: Aggregated risk rollups in `domain_summary.json` and
`leaderboard_rows.jsonl` should group by risk domain.

**Dashboard**: The web monitor should show risk-domain rollups as a first-class
view, not just benchmark-level scores.

### Static vs dynamic risk scenarios

**Static benchmarks** (current model): Pre-defined task sets with fixed prompts
and expected outcomes. Easy to reproduce, but may become stale.

**Dynamic scenarios** (future): Generated on-the-fly based on risk templates,
model capabilities, and red-team strategies. Requires:
- Scenario templates with variable parameters
- LLM-assisted scenario generation (adversarial prompt synthesis)
- Validation pipeline to ensure scenario quality
- Caching and versioning for reproducibility

Implementation approach: Add a `DynamicBenchmarkAdapter` base class that
generates scenarios at eval time, with seeded randomization for reproducibility.

---

## 4. Plugin Packaging

### Plugin types

| Plugin type | Registration point | Example |
|-------------|-------------------|---------|
| Benchmark adapter | `BenchmarkRegistry` | `snowl-bench-cybermetric` |
| Scorer | Scorer registry (new) | `snowl-scorer-cbrn` |
| Agent framework adapter | Agent adapter registry (new) | `snowl-agent-langgraph` |
| Environment launcher | `ContainerProviderRegistry` | `snowl-env-browser` |
| Exporter/dashboard | Export registry (new) | `snowl-export-mitre` |

### Discovery mechanism

Use Python entry_points for plugin discovery:

```toml
# In snowl-bench-cybermetric/pyproject.toml
[project.entry-points."snowl.benchmark"]
cybermetric = "snowl_bench_cybermetric:register"
```

Snowl's registry scans entry_points at startup:

```python
# In snowl/benchmarks/registry.py
import importlib.metadata

def discover_plugins():
    for ep in importlib.metadata.entry_points(group="snowl.benchmark"):
        adapter = ep.load()()
        register(ep.name, adapter)
```

### Version compatibility policy

- Plugins declare compatible Snowl core version ranges via `snowl>=0.1.0,<0.2.0`
- Core contracts (`Task`, `Agent`, `Scorer`, etc.) follow semver
- Breaking changes to core protocols require a major version bump
- Plugins can optionally declare their own version for artifact compatibility

### Package structure

```
snowl-bench-<name>/
  pyproject.toml          # declares snowl.benchmark entry point
  snowl_bench_<name>/
    __init__.py            # register() function
    adapter.py             # BenchmarkAdapter implementation
    scorer.py              # benchmark-specific scorers
    assets/                # dataset files (if bundled)
```

---

## 5. Backward Compatibility

### Current project.yml workflows that must keep working

1. **Single-benchmark eval**: `snowl eval project.yml` with `eval.benchmark` field
2. **Multi-model sweep**: `agent_matrix.models` with model entries
3. **Benchmark adapter mode**: `snowl bench run <name> --project project.yml`
4. **Suite mode**: `snowl suite run suite.yml`
5. **Retry mode**: `snowl retry <run_id> --project project.yml`
6. **Custom code modules**: `eval.code.task_module`, `agent_module`, `scorer_module`
7. **Runtime controls**: `max_running_trials`, `max_container_slots`, `provider_budgets`
8. **Container-backed benchmarks**: TerminalBench, OSWorld, ToolEmu emulation

### Adding new abstractions without breaking existing examples

**Rule**: New features are additive. Existing fields in `project.yml` keep their
semantics. New fields have sensible defaults.

| New abstraction | Impact on existing project.yml |
|-----------------|-------------------------------|
| `EnvironmentBlueprint` | None — blueprints are internal; project.yml still uses `env_type` |
| `AgentAdapterRegistry` | None — agents still use `agent_module`; adapters are for framework integration |
| `RiskDomain` metadata | Additive — `risk_domains` field in benchmark info; no project.yml change |
| Plugin entry_points | Additive — built-in benchmarks still work; plugins add to registry |
| Dynamic benchmark adapter | Additive — new adapter type; existing adapters unchanged |

**Migration path for breaking changes**:

1. Introduce new field/behavior alongside old one
2. Deprecate old field with a warning for one minor version
3. Remove old field in the next major version
4. Provide migration script if needed

---

## Implementation Rounds

### Round 2A: Agent Adapter SDK skeleton

1. Create `snowl/adapters/` package with `BaseAgentAdapter`
2. Implement OpenAI SDK adapter as reference
3. Add `AgentAdapterRegistry` for framework adapter discovery
4. Add integration tests with mock agent frameworks
5. Document adapter authoring guide

### Round 2B: Environment Blueprint contract

1. Define `EnvironmentBlueprint` dataclass in `snowl.core.env`
2. Define `EnvironmentLauncher` protocol
3. Migrate `ContainerProvider` → `EnvironmentLauncher` (with backward compat)
4. Refactor `container_providers.py` to use registry-based lookup instead of direct imports
5. Remove `runtime → benchmarks.osworld` boundary violation (H1 from audit)

### Round 2C: Frontier risk metadata + dashboard rollup

1. Add `RiskDomain` to `BenchmarkInfo`
2. Tag existing benchmarks with their risk domains
3. Update aggregation to group by risk domain
4. Add risk domain rollup views to web monitor
5. Add `DynamicBenchmarkAdapter` base class

### Round 2D: Plugin packaging and example adapters

1. Add entry_points-based plugin discovery to `BenchmarkRegistry`
2. Create `snowl-agent-langgraph` example plugin package
3. Create `snowl-agent-openai-sdk` example plugin package
4. Add scorer and exporter plugin registration points
5. Document plugin authoring guide

### Round 2E: Docs/tutorial polish and public API stabilization

1. Add interactive tutorial notebooks
2. Stabilize internal APIs that are ready for public use (ToolMiddleware, PlanBuilder, etc.)
3. Add `CHANGELOG.md`
4. Complete missing docs (testing, compatibility, release process)
5. Add `.github/pull_request_template.md`
6. Fix `test_benchmark_dependency_guard` failure (ToolEmu scorer isolation)
