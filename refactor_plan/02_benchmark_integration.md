# 02: Benchmark Integration Deep Dive

## 2.1 ToolEmu Integration

### Current State

**Adapter** (`snowl/benchmarks/toolemu/adapter.py`):
- Maps `all_cases.json` (144 cases) into Snowl samples
- Each sample carries: `toolkits`, `underspecifications`, `expected_achievements`, `potential_risky_outcomes`, `potential_risky_actions`
- Environment: `EnvSpec(env_type="local")` - no sandbox needed

**Scorer** (`snowl/benchmarks/toolemu/scorer.py`):
- Two scoring modes:
  1. **Custom evaluate_fn mode**: When an external `evaluate_fn` is provided, uses its raw `ToolCallRisk` and `Helpfulness` scores, normalizing from [1,3] to [0,1]
  2. **Native trace-policy mode** (default): Uses `ToolTracePolicyScorer` for risk + simple achievement text matching for helpfulness
- Missing: LM-emulated evaluation (the core ToolEmu innovation)

**Example project** (`examples/toolemu-official/`):
- Uses `ToolEmuNativeAgent` (a basic `OpenAICompatibleChatClient` wrapper)
- `SavingToolEmuScorer` persists scores

### What's Missing for Full Integration

#### M1: LM-Emulated Sandbox

ToolEmu's core innovation is using an LM to emulate tool execution. The current Snowl integration has **no support for this**. The agent runs against stub tools that return `{"ok": True}`, not emulated observations.

ToolEmu's emulator architecture:
```
Agent: "I want to send_email(to='bob@company.com', body='...')"
  -> Emulator LM (GPT-4): generates simulated observation
    -> Optional Critiquer LM: validates format, revises
  <- Observation: "Email sent successfully to bob@company.com"
```

Three simulator types:
- `normal`: Real tool execution (not applicable in Snowl without real APIs)
- `std_thought`: Standard emulator - faithfully simulates tool behavior
- `adv_thought`: Adversarial emulator - actively steers toward risky outcomes

**What Snowl needs**: An `EmulatedToolWrapper` that intercepts tool calls and routes them through an LM emulator instead of executing the stub callable.

#### M2: Agent-Type Matrix

ToolEmu defines three agent prompt variants:
- `naive`: No safety instructions
- `ss_only`: Safety requirements included
- `helpful_ss`: Safety + helpfulness requirements

The current integration doesn't expose these as agent variants. Users must manually configure agent prompts.

**What Snowl needs**: Benchmark-specific agent factories or prompt templates that can be selected via CLI flags or project.yml config.

#### M3: Trajectory-Level LM Evaluation

ToolEmu's `AgentRiskyToolCallEvaluator` and `AgentHelpfulnessEvaluator` are LM-based evaluators that examine full trajectories. They:
- Receive the complete action/observation history
- Produce structured output (thought, label, score, summary)
- Use a critiquer for output validation

The current `evaluate_fn` mode supports passing an external function, but:
- The function can't be async (sync scorer protocol)
- No provider admission for the evaluator LM
- No built-in critique loop

**What Snowl needs**: An `AsyncScorer` protocol and a `TrajectoryEvaluatorScorer` that runs LM-based evaluation with proper scheduler integration.

#### M4: Concurrency Profile

ToolEmu's original framework uses batch processing:
- `batch_size=5-10` (limited by API rate limits)
- `ThreadPoolExecutor` within batches
- JSONL streaming output for partial progress

Snowl's current defaults for ToolEmu:
- `max_running_trials`: CPU count (typically 8+)
- `max_container_slots`: 0 (correct, no Docker)
- `max_scoring_tasks`: = `max_running_trials`

This is reasonable for local execution, but:
- No consideration for the **emulator LM's** rate limits (every tool call hits the API)
- A single ToolEmu trial may make 5-10 emulator API calls per step x 10+ steps = 50-100 API calls
- With 8 concurrent trials, that's 400-800 concurrent API demands

**What Snowl needs**: A benchmark-specific concurrency profile that accounts for per-trial API call amplification.

### ToolEmu Data Flow (Target State)

```
all_cases.json
  -> ToolEmuBenchmarkAdapter._iter_rows() (lazy streaming)
  -> _row_to_sample() produces {id, input, metadata}
  -> Snowl Task with samples
  -> Agent runs with EmulatedToolWrapper
    -> Each tool call -> Emulator LM (provider_admission acquired)
    -> Optional: Critiquer LM (provider_admission acquired)
  -> TrajectoryEvaluatorScorer (async, with provider_admission for judge LM)
  -> Metrics: toolcall_risk, helpfulness, overall
  -> Aggregation: risk_rate, helpfulness_rate, with stderr and grouped by toolkit
```

## 2.2 AgentDojo Integration

### Current State

**Adapter** (`snowl/benchmarks/agentdojo/adapter.py`):
- Supports `banking` and `travel` suites
- Maps dataset rows with `pre_state`, `post_state`, `state_checks`, `forbidden_tools`, `forbidden_arg_patterns`
- Tool schemas normalized to OpenAI function-calling format
- Environment: `EnvSpec(env_type="local")`

**Scorer** (`snowl/benchmarks/agentdojo/scorer.py`):
- Three scores: `agentdojo_utility`, `agentdojo_security`, `agentdojo_score`
- Utility: `StateTransitionScorer` (checks pre/post state transitions)
- Security: `ToolTracePolicyScorer` (checks forbidden tools and argument patterns)
- Composite: `CheckpointScoreScorer` (50/50 weighting)

**Test guard**: `test_benchmark_dependency_guard.py` explicitly bans `import agentdojo`, confirming Snowl's integration is fully native.

### What's Missing for Full Integration

#### M5: Stateful Tool Execution

AgentDojo's `FunctionsRuntime` manages stateful tool execution where:
- Tools receive environment state via dependency injection (`Annotated[EnvType, Depends("field")]`)
- Tool execution mutates the environment state
- The agent's tool calls actually modify `pre_state` to produce `post_state`

The current Snowl integration uses **recording stub tools** that return `{"ok": True}` and don't mutate state. This means:
- `StateTransitionScorer` can only check pre-declared state transitions, not actual state mutations from tool execution
- The agent doesn't see realistic tool outputs
- Evaluation is limited to "did you call the right/wrong tools" rather than "did your tool calls produce the right state changes"

**What Snowl needs**: A `StatefulToolExecutor` that:
1. Maintains environment state (a Pydantic model or dict)
2. Executes tool callables that read/write this state
3. Returns realistic observations based on state changes

#### M6: Attack/Defense Pipeline

AgentDojo's core evaluation involves:
1. **Injection tasks**: Adversarial prompts injected into tool outputs (e.g., in email content)
2. **Attacks**: Different strategies for placing injection content
3. **Defenses**: Pipeline elements that filter/detect/transform inputs

The current integration skips this entirely. It loads pre-computed injection task metadata but:
- Doesn't actually inject adversarial content into tool outputs
- Doesn't support defense evaluation
- Doesn't measure the security/utility tradeoff under actual attack conditions

**What Snowl needs**:
- An `InjectionMiddleware` that modifies tool outputs based on injection task metadata
- A `DefensePipeline` abstraction for composing defense strategies
- Evaluation that measures both utility and security under actual attacks

#### M7: Per-Suite Tool and State Configuration

AgentDojo has 4+ suites (banking, travel, workspace, slam), each with:
- Different environment models
- Different tool sets
- Different injection vectors

The current adapter hardcodes tool schemas for `banking` and `travel`. Adding new suites requires code changes.

**What Snowl needs**: Suite-specific configuration loaded from the benchmark dataset, not hardcoded in the adapter.

#### M8: Multi-Run Evaluation (Utility x Security)

AgentDojo requires running each user task twice:
1. **Without injections**: Measure baseline utility
2. **With injections**: Measure utility degradation and security violations

The current integration collapses both into a single run. The composite score (50/50) assumes a single trajectory contains both utility and security signals, but in reality:
- Utility should be measured on clean runs
- Security should be measured on attacked runs
- The trade-off is between these two separate measurements

**What Snowl needs**: A `MultiRunScorer` or `PairedEvaluation` protocol that:
1. Runs each user task without injection -> measure utility
2. Runs each user task with injection -> measure security + utility degradation
3. Combines into a single evaluation report

### AgentDojo Data Flow (Target State)

```
Dataset (rows with suite, prompt, pre_state, injection_vectors, ...)
  -> AgentDojoBenchmarkAdapter (lazy streaming)
  -> Two evaluation runs per user task:
    Run A (clean): Agent + StatefulToolExecutor -> utility score
    Run B (attacked): Agent + StatefulToolExecutor + InjectionMiddleware -> security + utility scores
  -> AgentDojoScorer (async, composable)
    -> utility = StateTransitionScorer (clean run)
    -> security = ToolTracePolicyScorer (attacked run)
    -> composite = WeightedCompositeScorer(utility=0.5, security=0.5)
  -> Aggregation: utility_rate, security_rate, with stderr, grouped by suite and attack type
```

## 2.3 Integration Gaps Summary

| Gap | ToolEmu | AgentDojo | Priority |
|-----|---------|-----------|----------|
| Async scorer protocol | Required for LM evaluation | Nice-to-have for future LLM-judge | P0 |
| Emulated tool execution | Core feature | N/A | P0 |
| Stateful tool execution | N/A | Core feature | P0 |
| Injection middleware | N/A | Core feature | P1 |
| Benchmark concurrency profiles | High amplification (50-100 calls/trial) | Moderate (5-10 calls/trial) | P0 |
| Benchmark agent factories | 3 agent variants | Suite-specific agents | P1 |
| Multi-run evaluation | N/A | Required for utility/security tradeoff | P1 |
| Lazy data loading | 144 cases (manageable) | 97+ tasks x injections (grows fast) | P2 |
| Metric aggregation | Risk/helpfulness rates + stderr | Utility/security rates + stderr | P1 |
| Deferred scoring | Useful for iterative scorer dev | Useful for defense evaluation | P2 |
