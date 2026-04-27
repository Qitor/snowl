# Snowl 下一版本整体架构重构思考

本文基于对当前仓库文档与核心代码的整体阅读，目标不是提出一次“大爆炸重写”，而是回答一个更重要的问题：Snowl 如何从当前“可运行多个智能体基准的本地评测框架”，演进为一个更可扩展、更好用、面向智能体动态安全测试的开源框架。

目标成果可以表述为：

> 智能体动态安全测试风洞 Snowl：面向待测目标动态生成安全测试用例与测试环境，原生支持创智 Nexau、OpenAI SDK、LangGraph 等智能体框架快速接入，适配 10+ 第三方及自研测试基准，支持自动评测任务合成，覆盖 PC、Mobile、Terminal、Web 等多种执行环境，解决基准测试不统一、自研智能体难接入、测试集易老化等痛点。

本文只做分析和设计建议，不改变现有代码。

## 1. 阅读范围与当前事实

重点阅读了以下内容：

- `docs/project_map.md`
- `docs/current_state.md`
- `docs/architecture/runtime_and_scheduler.md`
- `README.md`
- `START_HERE.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `docs/risk_monitor_data_model.md`
- `docs/benchmark_taxonomy.md`
- `docs/benchmark_onboarding_playbook.md`
- `snowl/eval.py`
- `snowl/runtime/engine.py`
- `snowl/runtime/resource_scheduler.py`
- `snowl/runtime/container_runtime.py`
- `snowl/runtime/container_contract.py`
- `snowl/project_config.py`
- `snowl/bench.py`
- `snowl/benchmarks/base.py`
- `snowl/benchmarks/base_adapter.py`
- `snowl/benchmarks/registry.py`
- `snowl/aggregator/summary.py`
- `snowl/web/monitor.py`
- `webui/src/server/monitor.ts`
- `snowl/agents/*`
- `snowl/envs/*`
- TerminalBench / OSWorld 等代表性 benchmark adapter 与 example project。

当前 Snowl 已经具备很重要的平台雏形：

- 以 `project.yml` 作为入口。
- 以 `Task x AgentVariant x Sample` 作为核心执行单元。
- 有 `Task`、`Agent`、`Scorer`、`ToolSpec` 等核心契约。
- 有内置 OpenAI-compatible provider client。
- 有 `agent_matrix.models` 的多模型扫测能力。
- 有 StrongReject、TerminalBench、OSWorld、ToolEmu、AgentSafetyBench、WMDP、MASK、JSONL、CSV 等 benchmark adapter。
- 有本地单机调度器，支持 `max_running_trials`、`max_container_slots`、`max_builds`、`max_scoring_tasks`、`provider_budgets`。
- 有 TerminalBench / OSWorld 的 runtime-managed container contract 与 lifecycle manager。
- 有 `.snowl/runs/<run_id>/` artifact 体系。
- 有 CLI 与 Next.js Web monitor。
- 有风险看板 v2 数据模型，包括 benchmark/domain/leaderboard rollup。

这说明 Snowl 不再是简单 benchmark wrapper，而已经接近一个“评测执行平台”。下一版的关键不是继续堆 adapter，而是把动态生成、环境编排、智能体接入、调度和评测治理抽象成稳定平台层。

## 2. 当前架构的优点

### 2.1 核心执行单元选得对

`Task x AgentVariant x Sample` 是一个很稳的抽象。它能覆盖：

- 单题 QA。
- 多模型对比。
- 一个 benchmark 下多个样本。
- 一个 agent 在不同模型、参数、来源下的变体。
- Terminal / GUI / tool-use 等差异化环境。

建议保留这个执行单元，但下一版需要把它升级为更完整的 trial graph：不仅有 sample，还要有生成 recipe、环境蓝图、资源需求、证据采集策略、评分套件和复现信息。

### 2.2 `project.yml` 入口有利于可复现

当前文档和代码都在强调 YAML-first，这是正确方向。对评测框架来说，入口配置本身就是实验声明，应该可审计、可 diff、可归档。

但当前 `project.yml` 仍偏“单次运行配置”，下一版应演进为“实验规格说明”：

- 多 provider。
- 多 agent framework。
- 多 benchmark / 多 generator。
- 多环境 profile。
- 多 scorer suite。
- 数据与环境版本锁定。
- 风险领域和评测目标显式声明。

### 2.3 runtime / scheduler 已经意识到资源不是一种东西

现在已经拆出了：

- running trial
- container slot
- build slot
- scoring task
- provider budget

这是对的。智能体评测的瓶颈通常不是 CPU，而是 provider 并发、容器启动、浏览器实例、移动模拟器、GUI 环境、judge 调用、外部服务 quota 等资源。下一版应把这个方向推进到“资源图 + 阶段图”的调度模型。

### 2.4 artifact 和 observability 方向正确

`.snowl/runs/<run_id>/` 目前已经包含：

- `manifest.json`
- `plan.json`
- `events.jsonl`
- `runtime_state.json`
- `profiling.json`
- `outcomes.json`
- `trials.jsonl`
- `aggregate.json`
- `benchmark_summary.json`
- `domain_summary.json`
- `leaderboard_rows.jsonl`

这条链路能支撑研究复现、Web monitor 和后处理。下一版应把 artifact schema 进一步版本化，并把“证据包”作为一等产物，而不是只在 trace/payload 里零散出现。

### 2.5 Benchmark taxonomy 已经开始平台化

`BenchmarkInfo`、domain、benchmark_type、primary_metric、preview mode、dashboard tags 等已经是很好的起点。下一版应进一步支持：

- 风险领域本体。
- benchmark capability/safety 双轴。
- metric direction 与归一化策略。
- benchmark lineage/version。
- generated benchmark 与 static benchmark 的统一元数据。
- sample provenance。

## 3. 当前架构与目标之间的结构性差距

目标里最重要的几个词是“动态生成”“测试环境生成”“原生支持多智能体框架”“10+ 基准”“PC/Mobile/Terminal/Web 多环境”“测试集易老化”。对照当前代码，差距主要不在功能数量，而在抽象层级。

### 3.1 `eval.py` 是事实上的控制平面，但职责过重

`snowl/eval.py` 当前同时承担：

- project/config 解析后的组件加载。
- task/agent/scorer discovery。
- plan 构建。
- runtime budget 解析。
- scheduler 创建和 provider hook 安装。
- run artifact bootstrap。
- live events 写入。
- retry/recovery ledger。
- trial coroutine dispatch。
- checkpoint/resume。
- summary/aggregate artifact 写入。
- renderer/Web monitor 支持。

这在早期非常高效，但下一版要支持动态生成、插件、分布式、多环境和更复杂的 retry 时，会变成演进瓶颈。

建议重构方向：

- `snowl/eval.py` 保持 CLI/API 入口。
- 抽出 `Planner`：负责从 EvalSpec 生成 TrialPlan。
- 抽出 `RunController`：负责 run lifecycle、事件、artifact、recovery。
- 抽出 `Scheduler`：负责 phase admission 与队列策略。
- 抽出 `TrialExecutor`：负责执行一个 trial phase graph。
- 抽出 `ArtifactStore`：负责 schema 化持久化。
- 抽出 `EventBus`：负责 runtime events 的规范化、订阅与持久化。

### 3.2 Benchmark adapter 还是静态数据集入口，不是“任务源”平台

当前 benchmark adapter 的核心是 `load_tasks(split, limit, filters)`。它适合静态 benchmark，但“动态安全测试风洞”需要更宽的任务源模型：

- 静态基准数据集。
- 基于 seed corpus 的变异生成。
- 基于目标 agent 行为的自适应生成。
- 基于风险模型的场景组合生成。
- 基于环境蓝图的任务合成。
- 回归样本库。
- 人工审核后的 curated suite。

也就是说，benchmark adapter 应演进为 `TaskSource` 或 `ScenarioProvider`：

- 可以返回静态 samples。
- 可以流式生成 samples。
- 可以声明生成 recipe。
- 可以声明覆盖目标和停止条件。
- 可以输出 provenance 和 dedup hash。
- 可以声明环境需求。

### 3.3 动态测试用例生成目前不是一等概念

当前 sample 是 adapter 产物，runtime 只消费 sample。没有明确的：

- `TestGenerator`
- `GenerationRecipe`
- `Scenario`
- `Mutation`
- `CoverageObjective`
- `GeneratedSampleLineage`
- `Aging/Dedup/Novelty` 策略

如果要解决“测试集易老化”，必须让“生成过程”可复现、可度量、可审计。仅仅把 LLM 生成的问题写入 JSONL 不够，因为无法回答：

- 这个样本从哪里来？
- 对应哪个风险域？
- 由哪个 prompt/template/model/seed 生成？
- 是否是已有样本变体？
- 与历史失败样本有什么关系？
- 什么时候应该淘汰或降权？
- 是否被人工审核过？
- 是否可能泄漏 benchmark 答案？

### 3.4 环境生成目前主要是 benchmark-specific provider

TerminalBench / OSWorld 已经有 `runtime_container` contract，这是很好的方向。但当前环境生成仍主要表现为：

- adapter 在 sample metadata 里写 `runtime_container`。
- runtime 根据 benchmark/provider_name 找 provider。
- provider 负责具体启动容器。

下一版目标是 PC、Mobile、Terminal、Web 多环境，不能只靠 benchmark-specific provider 扩展。需要一个统一的 `EnvironmentBlueprint`：

- 环境类型：local / terminal / web / desktop / mobile / hybrid。
- 基础镜像或设备 profile。
- 初始状态：文件、浏览器 profile、app 安装包、桌面快照、账号、网络条件。
- 可观测通道：screenshot、DOM、accessibility tree、terminal output、network logs、video、trace。
- 动作空间：click/type/key/scroll/shell/browser/tool/api/mobile gestures。
- 重置策略：snapshot、container rebuild、simulator reset、browser context reset。
- 安全边界：网络隔离、secret mount、egress policy、filesystem policy。
- 资源需求：CPU、memory、GPU/KVM、ports、provider quotas。

### 3.5 智能体框架接入仍是“用户写 Agent.run”

当前 native contract 是：

```python
async def run(state: AgentState, context: AgentContext, tools=None) -> AgentState
```

这是一个很好的最低层协议，但目标要求“原生支持创智 Nexau、OpenAI SDK、LangGraph 等框架快速接入”。这意味着需要 adapter SDK，而不应要求用户手写大量 glue code。

下一版需要至少支持几类 Subject Agent：

- In-process Python agent。
- HTTP/gRPC 服务型 agent。
- CLI/process agent。
- OpenAI SDK Agents/Responses 风格 agent。
- LangGraph graph app。
- Nexau agent。
- 浏览器/桌面自动化 agent。
- 黑盒远程 agent。

核心不是把所有框架写死进 runtime，而是定义 `AgentAdapter` 协议：

- 如何启动/连接 agent。
- 如何传入 task。
- 如何暴露 tools。
- 如何接收 actions/messages。
- 如何取消。
- 如何采集 trace。
- 如何做健康检查。
- 如何隔离 secret。
- 如何声明资源需求。

### 3.6 Provider 模型过窄

当前 `ProjectProviderConfig` 只支持一个 `provider.kind: openai_compatible`。代码里虽然有 per-model `provider` override，但 `provider_id` 仍沿用全局 provider，尚不是多 provider 控制平面。

目标里的智能体评测会同时需要：

- agent 模型 provider。
- judge 模型 provider。
- generator 模型 provider。
- embedding/dedup provider。
- target agent 服务 endpoint。
- browser/mobile/desktop provider。
- secret provider。

下一版应该把 provider 改为具名列表：

```yaml
providers:
  openai:
    kind: openai
  siliconflow:
    kind: openai_compatible
  local_vllm:
    kind: openai_compatible
  browser_pool:
    kind: playwright
  android_pool:
    kind: android_emulator
```

然后 agent、judge、generator、environment、scorer 分别引用 provider id。

### 3.7 Scorer 体系还是“一个 scorer 对一个 trial”

当前 `run_eval_with_components(..., scorer=components.scorers[0])` 实际只用第一个 scorer。`ScoreMap` 支持多 metric，但 scorer suite 不是一等概念。

安全评测通常需要组合评分：

- 规则评分。
- 单元测试/环境成功率。
- judge 模型评分。
- policy classifier。
- trajectory risk classifier。
- 人审字段。
- evidence completeness。
- confidence / uncertainty。

下一版应引入 `ScorerSuite`：

- 多 scorer 并行或串行。
- scorer dependency graph。
- judge provider budget 单独控制。
- metric normalization。
- verdict policy。
- disagreement reporting。
- calibration set。
- audit evidence。

### 3.8 Observability 还偏 run-first，不够 experiment/generation-first

当前 Web monitor 很有用，但主要从 run artifact 和 events 读数据。目标里的“风洞”需要额外可视化：

- 测试用例生成过程。
- 风险域覆盖。
- 环境生成/启动拓扑。
- agent 行为轨迹。
- 安全失败类型聚类。
- 样本老化和重复率。
- benchmark 版本和数据 lineage。
- 多 run / 多模型 / 多 benchmark 试验矩阵。

也就是说，下一版 Web UI 需要从“运行监控器”升级为“评测操作台 + 风险分析台 + 样本治理台”。

## 4. 下一版核心产品模型

建议把 Snowl 下一版的心智模型定义为：

```text
EvalSpec
  -> TaskSource / TestGenerator
  -> Scenario + EnvironmentBlueprint
  -> TrialPlan
  -> Phase-aware Runtime
  -> EvidenceBundle
  -> ScorerSuite
  -> Risk / Capability Rollups
  -> Reports + Dataset Feedback Loop
```

其中：

- `EvalSpec` 是用户声明的实验目标。
- `TaskSource` 统一静态 benchmark 和动态生成。
- `TestGenerator` 负责根据风险目标生成或变异测试样本。
- `Scenario` 是语义层的测试场景。
- `EnvironmentBlueprint` 是可执行环境声明。
- `TrialPlan` 是可调度、可复现的执行计划。
- `EvidenceBundle` 是一次 trial 的完整证据。
- `ScorerSuite` 是评分图。
- Rollups 是面向 benchmark/domain/model 的分析产物。
- Feedback Loop 把失败样本、novel cases、人工审核结果反哺生成器和回归集。

## 5. 建议的分层架构

### 5.1 Layer 1：公共领域模型与 schema

当前 `snowl/core/` 已有基础。下一版建议扩展为以下领域模型：

```text
snowl/core/
  eval_spec.py
  subject.py
  task.py
  scenario.py
  environment.py
  generator.py
  scorer.py
  evidence.py
  artifact.py
  event.py
```

关键对象：

- `EvalSpec`：一次评测/实验的声明。
- `Subject`：待测目标，可以是模型、agent、服务、graph、应用。
- `AgentAdapterSpec`：如何接入待测目标。
- `TaskSourceSpec`：静态 benchmark、JSONL、CSV、HF dataset、自研 task provider、动态 generator。
- `Scenario`：语义测试用例，不绑定具体执行环境。
- `Sample`：scenario 的一次具体实例化。
- `EnvironmentBlueprint`：环境构建与重置声明。
- `ToolSurface`：agent 可用工具和环境动作空间。
- `TrialDescriptor`：一个具体 trial 的稳定身份。
- `TrialPlan`：phase graph + resource requirements。
- `EvidenceBundle`：trace、logs、screenshots、video、network、files、model I/O、tool I/O。
- `ScoreBundle`：多 scorer 结果、解释、置信度和 verdict。

设计原则：

- 所有对象都应该有 schema version。
- 所有对象都应该能 JSON 序列化。
- 用户可见 ID 必须稳定。
- 自动生成产物必须有 lineage。
- runtime 私有字段和用户输入字段要分开，避免 metadata 继续膨胀成隐式协议。

### 5.2 Layer 2：Agent Adapter SDK

目标是让用户“不理解 Snowl 内部也能接入自己的智能体”。

建议定义统一协议：

```python
class AgentAdapter:
    adapter_id: str

    async def prepare(self, subject, run_context) -> AgentHandle: ...
    async def start_trial(self, handle, trial_context) -> None: ...
    async def send_observation(self, handle, observation) -> AgentAction: ...
    async def run_to_completion(self, handle, trial_context) -> AgentResult: ...
    async def cancel(self, handle) -> None: ...
    async def close(self, handle) -> None: ...
```

并提供内置 adapters：

- `snowl.adapters.openai_sdk`
- `snowl.adapters.langgraph`
- `snowl.adapters.nexau`
- `snowl.adapters.http`
- `snowl.adapters.cli`
- `snowl.adapters.python_callable`
- `snowl.adapters.openai_compatible_chat`
- `snowl.adapters.browser_agent`

#### OpenAI SDK 接入

重点能力：

- 支持 OpenAI SDK 的模型调用、工具调用、response trace。
- 能把 Snowl `ToolSpec` 映射到 OpenAI tools。
- 能捕获 request/response、tool call、usage。
- 能复用 Snowl provider budgets。

#### LangGraph 接入

重点能力：

- 接入 compiled graph 或 factory。
- 将 Snowl task input 转成 graph state。
- 将环境观察转成 graph node input。
- 捕获 node transition、checkpoint、interrupt。
- 支持 LangGraph 自身 checkpoint 与 Snowl recovery 的映射。

#### Nexau 接入

由于目标明确提到创智 Nexau，应把它作为一等 adapter，而不是示例代码。建议至少支持：

- Nexau agent/package 的声明式加载。
- Nexau runtime endpoint 的远程接入。
- Snowl ToolSpec 与 Nexau tool/action schema 的互转。
- Nexau trace 与 Snowl EvidenceBundle 的互转。
- Nexau provider/resource 配额映射。

即使初期不实现全部，也要先把 adapter boundary 留对。

#### 黑盒 agent 接入

开源框架要面对大量非 Python agent。建议支持：

```yaml
subjects:
  my_agent:
    adapter: http
    endpoint: http://localhost:9000/run
    protocol: snowl-agent-v1
```

以及：

```yaml
subjects:
  cli_agent:
    adapter: process
    command: ["python", "run_agent.py", "--json"]
```

提供标准 JSON 协议，用户只需要实现 stdin/stdout 或 HTTP endpoint。

### 5.3 Layer 3：TaskSource 与 TestGenerator

这是实现“动态安全测试风洞”的核心。

当前 benchmark adapter 可以成为 `StaticTaskSource` 的一种。下一版建议：

```python
class TaskSource:
    def info(self) -> TaskSourceInfo: ...
    def list_splits(self) -> list[str]: ...
    def iter_scenarios(self, query: ScenarioQuery) -> Iterator[Scenario]: ...

class TestGenerator:
    def plan(self, objective: GenerationObjective) -> GenerationPlan: ...
    async def generate(self, plan: GenerationPlan) -> AsyncIterator[GeneratedScenario]: ...
```

#### 生成器类型

1. Seed corpus generator
   从 StrongReject、WMDP、MASK、ToolEmu 等已有 benchmark 中抽取 seed，进行变异、组合、重写。

2. Risk template generator
   按风险域、攻击链、工具能力、环境类型生成任务。

3. Adaptive generator
   根据目标 agent 历史失败/成功行为，选择更难或更相关的 case。

4. Environment-coupled generator
   生成任务时同时生成环境蓝图，例如 Web 应用漏洞场景、Terminal 文件系统任务、Mobile App 操作场景。

5. Regression generator
   从历史失败样本、人工审核样本、线上 incident 中构建回归集。

6. Metamorphic generator
   针对同一语义目标生成多个等价变体，用于检查 agent 行为一致性。

#### 生成产物必须包含 lineage

建议每个 generated scenario 包含：

```json
{
  "scenario_id": "...",
  "generator_id": "...",
  "generator_version": "...",
  "seed": 1234,
  "recipe_hash": "...",
  "source_benchmark": "strongreject",
  "source_sample_id": "...",
  "mutation_chain": ["translate", "roleplay", "tool_context"],
  "risk_domain": "agentic_safety",
  "capability_tags": ["tool_use", "browser"],
  "novelty_score": 0.82,
  "dedup_hash": "...",
  "created_at": "...",
  "review_status": "unreviewed"
}
```

#### 解决测试集老化

测试集老化不是单点功能，而是一套治理机制：

- 样本生成 recipe 版本化。
- 样本去重和相似度索引。
- 历史命中率追踪。
- 泄漏风险标记。
- 高频失败样本沉淀为 regression suite。
- 过于稳定或过于容易的样本降权。
- 生成器定期刷新。
- 人工审核和发布流程。
- public benchmark 与 private/generated suite 分层。

建议 Snowl 内部引入 `CaseBank`：

```text
.snowl/casebank/
  scenarios/
  generated/
  reviewed/
  regression/
  embeddings/
  lineage.jsonl
```

开源版本可以本地文件实现，未来再接数据库。

### 5.4 Layer 4：Environment Blueprint 与多环境执行

目标要覆盖 PC、Mobile、Terminal、Web。建议统一为：

```python
class EnvironmentProvider:
    provider_id: str
    supported_kinds: set[str]

    async def prepare(self, blueprint, trial_context) -> PreparedEnvironment: ...
    async def observe(self, env, channels) -> Observation: ...
    async def act(self, env, action) -> ActionResult: ...
    async def reset(self, env) -> ResetResult: ...
    async def teardown(self, env) -> TeardownResult: ...
```

环境种类建议：

- `local`
- `terminal`
- `web`
- `desktop`
- `mobile`
- `api`
- `hybrid`

#### Terminal

当前 TerminalBench 的 `TerminalEnv` 和 container provider 可以保留，但应迁入统一 provider 模型：

- Docker Compose provider。
- Plain shell provider。
- Remote SSH provider。
- Kubernetes job provider。

#### Web

建议引入 Playwright provider：

- browser context 隔离。
- DOM + screenshot + accessibility observation。
- network HAR。
- console log。
- storage state。
- route mocking。
- deterministic seed。
- local web app environment blueprint。

很多 agent 安全评测需要 Web 环境，例如 prompt injection、tool injection、browser-based data exfiltration、phishing UI、malicious web content。Web 应是一等环境，不应只被当作外部工具。

#### Desktop / PC

OSWorld 当前覆盖 GUI container，但下一版需要抽象成 desktop provider：

- Docker desktop provider。
- VM provider。
- Remote VNC/RDP provider。
- OSWorld-compatible provider。
- snapshot reset。
- screenshot/video/accessibility/terminal channels。

#### Mobile

Mobile 建议单独抽象：

- Android emulator provider。
- iOS simulator provider。
- Appium provider。
- ADB provider。
- mobile gestures。
- app install/reset。
- screenshot/accessibility/logcat/network channels。

Mobile 环境的成本和启动时间通常更高，所以必须与 scheduler resource model 对齐。

#### Environment Blueprint 示例

```yaml
environments:
  android_default:
    kind: mobile
    provider: android_emulator
    device: Pixel_7
    image: android-35
    apps:
      - path: ./apps/test.apk
    observation:
      - screenshot
      - accessibility
      - logcat
    reset:
      strategy: snapshot
    resources:
      cpu: 4
      memory_gb: 8
      emulator_slots: 1
```

### 5.5 Layer 5：Phase-aware Scheduler 与运行时控制平面

当前 scheduler 已有 phase API，但主 loop 尚未完全使用。下一版应让 trial 执行成为 phase graph：

```text
generate_case
  -> materialize_environment
  -> prepare_subject
  -> execute
  -> collect_evidence
  -> score
  -> finalize
  -> persist
```

每个 phase 都声明资源：

- model provider slots
- generator provider slots
- judge provider slots
- container slots
- browser slots
- mobile emulator slots
- build slots
- CPU/memory/GPU/KVM
- network namespace
- filesystem locks

#### 调度策略

建议从 FIFO 升级到 policy-driven queue：

- provider-aware dispatch：不要启动会马上卡在 provider budget 的 trial。
- environment locality：相同 `env_spec_hash` 的任务优先批处理或复用 warm pool。
- canary-first：大规模动态生成前先跑小样本。
- failure-aware retry：infra 失败和 semantic failure 区分。
- deadline/priority：交互式调试任务优先。
- fairness：不同模型/benchmark 不互相饿死。
- cost-aware：移动/桌面环境更贵，按资源成本入队。

#### warm pool

当前默认 destroy container 是保守合理的。下一版可以引入显式 warm pool：

- 只对声明可复用的 blueprint 启用。
- 按 `env_spec_hash` 分池。
- 污染检测。
- TTL 和 max lease。
- failed trial 自动标 dirty。
- UI 显示池状态。

#### phase-level retry

当前 retry 主要是 whole-trial。下一版建议：

- prepare retry。
- provider call retry。
- execute retry。
- score retry。
- evidence upload retry。
- finalize retry。

不同失败类别对应不同策略：

- container build fail：不要马上重跑 agent。
- judge timeout：只重跑 scoring。
- environment readiness fail：重建环境。
- agent semantic failure：不自动重跑，除非生成目标要求 stochastic sampling。

### 5.6 Layer 6：Benchmark / Plugin 生态

当前 registry 是代码内置表。下一版为了开源生态，应支持插件式发现：

- Python entry points。
- local plugin directory。
- Git repo install。
- benchmark package conformance test。

建议包形态：

```text
snowl_bench_mybench/
  pyproject.toml
  snowl_bench_mybench/
    adapter.py
    scorer.py
    metadata.yaml
    sample_preview.py
    environment.py
    tests/
```

entry point：

```toml
[project.entry-points."snowl.benchmarks"]
mybench = "snowl_bench_mybench:register"
```

Benchmark adapter 不应只返回 `Task`，而应声明：

- metadata。
- sample schema。
- scorer recommendations。
- environment requirements。
- supported preview modes。
- artifact/evidence expectations。
- conformance fixtures。

#### 10+ benchmark 适配策略

建议按“风险域 + 环境类型 + 接入复杂度”组织，而不是简单追求数量：

- QA/MCQ：WMDP Cyber、WMDP Chem。
- Dialog safety：StrongReject、MASK、AgentSafetyBench。
- Tool safety：ToolEmu。
- Terminal/code：TerminalBench。
- Desktop/PC：OSWorld。
- Web：新增 WebArena / MiniWoB / 自研 Web 安全任务。
- Mobile：新增 AndroidWorld / 自研 Mobile 安全任务。
- Cyber range：新增 CTF / sandboxed vulnerable service benchmark。
- Custom generated：Snowl Dynamic Safety Suite。

对外可以宣称“适配 10+ 第三方及自研基准”，但内部必须避免每个 benchmark 都绕过共享 contract。

### 5.7 Layer 7：ScorerSuite 与评测可信度

安全评测不能只看一个 metric。建议定义：

```yaml
scoring:
  suite: safety_default
  scorers:
    - id: rule_refusal
      kind: regex
    - id: judge
      kind: model_judge
      provider: openai
      model: gpt-4.1-mini
    - id: trajectory_risk
      kind: classifier
  verdict:
    policy: weighted
    thresholds:
      unsafe: 0.7
```

Scorer 输出建议包含：

- metric value。
- direction。
- normalized value。
- confidence。
- explanation。
- evidence refs。
- rubric version。
- judge prompt hash。
- calibration metadata。

#### 评分的可解释性

每个 trial 应形成 EvidenceBundle：

```text
evidence/
  model_io.jsonl
  tool_calls.jsonl
  actions.jsonl
  observations.jsonl
  screenshots/
  video/
  terminal.log
  network.har
  files/
  scorer_inputs.jsonl
  scorer_outputs.jsonl
```

Scorer 不应该只消费最终 output，而应该能消费 evidence refs。

### 5.8 Layer 8：ArtifactStore、EventBus 与数据湖

当前 artifact 文件已经可用，但 schema 分散。下一版建议有统一的 artifact store 接口：

```python
class ArtifactStore:
    def write_manifest(...)
    def append_event(...)
    def write_trial(...)
    def write_evidence(...)
    def write_score(...)
    def write_rollup(...)
```

本地实现仍可用 `.snowl/runs/`，但目录建议更结构化：

```text
.snowl/
  runs/
    <run_id>/
      manifest.json
      eval_spec.lock.json
      plan.json
      events.jsonl
      runtime_state.json
      trials/
        <trial_key>/
          descriptor.json
          attempts.jsonl
          evidence/
          scores.json
      rollups/
        aggregate.json
        benchmark_summary.json
        domain_summary.json
        leaderboard_rows.jsonl
      profiling.json
  experiments/
    <experiment_id>/
      manifest.json
      runs.jsonl
      rollups/
  casebank/
```

#### EventBus

建议定义规范 event envelope：

```json
{
  "schema_version": "event.v1",
  "run_id": "...",
  "experiment_id": "...",
  "trial_key": "...",
  "phase": "execute",
  "event": "agent.action",
  "ts_ms": 123,
  "level": "info",
  "payload": {},
  "resource": {},
  "refs": []
}
```

所有 runtime、agent adapter、environment provider、scorer 都只发标准事件。

### 5.9 Layer 9：Web UI 从 monitor 升级为评测工作台

建议 UI 分三层：

1. Operator Monitor
   关注 run 是否正常、资源是否阻塞、trial 是否失败、环境是否泄漏。

2. Evaluation Dashboard
   关注模型/agent/benchmark/domain 的风险与能力对比。

3. Case Lab
   关注动态生成样本、casebank、失败样本聚类、人工审核、回归集维护。

#### 关键页面建议

- `/runs`：运行列表。
- `/runs/[runId]`：运行工作台。
- `/experiments/[experimentId]`：实验矩阵。
- `/domains`：风险域总览。
- `/benchmarks`：基准库。
- `/cases`：样本库和生成历史。
- `/cases/[caseId]`：用例 lineage、证据、审核。
- `/generators`：生成器配置、覆盖率、产出质量。
- `/environments`：环境池、容器、浏览器、移动设备状态。
- `/subjects`：待测 agent/model 列表。

#### 当前 UI 数据模型可保留但需扩展

`RunRow`、`RunSnapshot`、`RuntimeEvent`、`DomainOverview`、`LeaderboardRow` 等类型很好。下一步新增：

- `CaseRow`
- `ScenarioRow`
- `GenerationRunRow`
- `EnvironmentLeaseRow`
- `EvidenceRef`
- `ScorerSuiteResult`
- `SubjectRow`

## 6. 下一版配置设计草案

建议把 `project.yml` 演进为更完整的 EvalSpec。示例：

```yaml
schema_version: snowl.eval.v2

project:
  name: dynamic-agent-safety-windtunnel
  root_dir: .

providers:
  openai:
    kind: openai
    api_key: ${OPENAI_API_KEY}
  siliconflow:
    kind: openai_compatible
    base_url: https://...
    api_key: ${SILICONFLOW_API_KEY}
  browser_local:
    kind: playwright
  android_pool:
    kind: android_emulator

subjects:
  target_langgraph_agent:
    adapter: langgraph
    module: ./agent_graph.py
    factory: build_graph
    provider: siliconflow
    models:
      - id: qwen3_32b
        model: Qwen/Qwen3-32B
        metadata:
          company: Alibaba
          country: CN
          source_type: open_source

task_sources:
  static_safety:
    kind: benchmark
    benchmarks:
      - strongreject
      - mask
      - agentsafetybench
    split: test
    limit_per_benchmark: 50

  dynamic_tool_safety:
    kind: generator
    generator: adversarial_tool_use_v1
    risk_domains:
      - agentic_safety
    seed_sources:
      - toolemu
      - strongreject
    budget:
      max_cases: 100
      novelty_threshold: 0.75

environments:
  terminal_default:
    kind: terminal
    provider: docker_compose
    resources:
      container_slots: 1

  web_default:
    kind: web
    provider: browser_local
    observation:
      - screenshot
      - dom
      - accessibility
      - network

  mobile_default:
    kind: mobile
    provider: android_pool
    observation:
      - screenshot
      - accessibility
      - logcat

scoring:
  suites:
    safety_suite:
      scorers:
        - kind: rule
        - kind: model_judge
          provider: openai
          model: gpt-4.1-mini
      verdict:
        policy: weighted

runtime:
  scheduler:
    max_running_trials: 8
    max_scoring_tasks: 8
    max_builds: 2
    resources:
      container_slots: 4
      browser_slots: 6
      mobile_slots: 2
    provider_budgets:
      openai: 8
      siliconflow: 8
  recovery:
    auto_retry_non_success: true
    max_auto_retries_per_trial: 1
    retry_timing: deferred
```

兼容策略：

- 现有 `project.yml` 作为 v1 继续支持。
- v2 loader 将旧字段映射到新 EvalSpec。
- 文档中明确 v1/v2 差异。
- 所有官方 examples 分批迁移。

## 7. 代码结构重构建议

建议从当前结构：

```text
snowl/eval.py
snowl/runtime/
snowl/benchmarks/
snowl/agents/
snowl/model/
snowl/web/
```

逐步演进为：

```text
snowl/
  core/
    contracts...
  config/
    eval_spec.py
    loader.py
    migration.py
  planning/
    planner.py
    trial_graph.py
    generation_planner.py
  runtime/
    controller.py
    executor.py
    scheduler.py
    phases.py
    resources.py
    recovery.py
  environments/
    base.py
    terminal.py
    web.py
    desktop.py
    mobile.py
    providers/
  adapters/
    base.py
    openai_sdk.py
    langgraph.py
    nexau.py
    http.py
    process.py
  generation/
    base.py
    recipes.py
    mutation.py
    dedup.py
    casebank.py
  benchmarks/
    base.py
    registry.py
    builtin/
  scoring/
    suite.py
    judge.py
    policies.py
  artifacts/
    store.py
    schemas.py
  observability/
    events.py
    monitor_index.py
  web/
```

不建议一次搬完。正确顺序是“先抽接口，再迁实现”。

## 8. 增量迁移路线

### Milestone A：契约硬化与拆分 `eval.py`

目标：不改变用户行为，但降低未来重构风险。

工作：

- 引入 `EvalSpec` 内部模型，v1 `project.yml` 加载后转换为 EvalSpec。
- 抽出 `PlanBuilder`，负责 `_build_plan` 与 trial descriptor。
- 抽出 `RunArtifactStore`，承接 `_write_*` 系列逻辑。
- 抽出 `RunEventBus`，承接 `_record_event`、event enrichment、synthetic pretask events。
- 抽出 `RecoveryManager`，承接 recovery ledger 与 retry queue 逻辑。

验收：

- 所有现有 eval/runtime/web tests 通过。
- artifact shape 保持兼容。
- `snowl eval` 与 `snowl bench run` 行为不变。

### Milestone B：多 provider 与 Agent Adapter SDK

目标：解决“自研智能体难接入”和“多框架接入”。

工作：

- `providers:` 列表配置。
- 保持 `provider:` v1 兼容。
- 引入 `SubjectSpec` 与 `AgentAdapter`。
- 内置 `python_callable`、`openai_compatible_chat`、`http`、`process` adapters。
- 增加 LangGraph adapter。
- 增加 Nexau adapter 骨架和 conformance tests。
- 把 OpenAI SDK adapter 作为官方路径之一。

验收：

- 一个无需写 Snowl Agent 类的 HTTP agent 可被评测。
- 一个 LangGraph 示例可运行。
- 当前 examples 仍可运行。

### Milestone C：Environment Blueprint

目标：统一 PC/Mobile/Terminal/Web 的环境契约。

工作：

- 定义 `EnvironmentBlueprint`、`PreparedEnvironment`、`Observation`、`Action`。
- 把 `runtime_container` contract 映射为 `EnvironmentBlueprint`。
- TerminalBench / OSWorld provider 迁到新接口后保留旧 metadata 兼容。
- 新增 Web Playwright provider。
- 新增 Mobile provider skeleton。

验收：

- TerminalBench / OSWorld 不回退。
- Web benchmark 示例可运行。
- 环境证据统一写入 EvidenceBundle。

### Milestone D：ScorerSuite 与 EvidenceBundle

目标：提升安全评测可信度和可解释性。

工作：

- 引入 `EvidenceBundle` 目录结构。
- 所有 agent/environment/scorer events 写 evidence refs。
- `scoring.suites` 支持多 scorer。
- judge prompt/rubric/version/hash 进入 artifact。
- Web UI trial detail 能展示 evidence refs。

验收：

- 一个 trial 可追溯完整 model I/O、tool I/O、环境观察、评分输入输出。
- 多 scorer 输出稳定进入 rollup。

### Milestone E：Dynamic Test Generator 与 CaseBank

目标：实现“动态生成安全测试用例”和“测试集抗老化”。

工作：

- 引入 `TestGenerator` 协议。
- 实现 seed mutation generator。
- 实现 risk template generator。
- 实现 local CaseBank。
- 引入 dedup hash、lineage、novelty score。
- 支持 `snowl generate` 与 `snowl eval` 中 inline generation。

验收：

- 可以从 StrongReject/ToolEmu seeds 动态生成新 cases。
- 生成样本可复现、可去重、可沉淀为 regression suite。
- Web UI 能查看 generation run 和 case lineage。

### Milestone F：Phase-aware Scheduler

目标：让大规模、多环境、多 provider 运行更可靠。

工作：

- 主 eval loop 改为 phase graph 调度。
- prepare/execute/score/finalize 独立 admission。
- provider-aware dispatch。
- env spec hash locality。
- warm pool 可选启用。
- phase-level retry。
- 更丰富 profiling。

验收：

- container-heavy benchmark 吞吐可量化提升。
- provider wait 不再大量发生在已占用 running trial slot 的状态。
- prepare/scoring/finalize 失败可独立诊断和重试。

### Milestone G：Plugin 生态与 10+ benchmark 稳定矩阵

目标：开源框架可扩展。

工作：

- entry point benchmark discovery。
- plugin conformance CLI。
- benchmark package template。
- 官方 benchmark compatibility matrix。
- benchmark onboarding CI。

验收：

- 外部 benchmark 无需改 Snowl core 即可安装运行。
- 10+ benchmark 在统一 metadata、artifact、dashboard 下展示。

## 9. 当前代码中值得尽快修正或明确的细节

这些不是本次改代码建议，但未来重构时需要注意。

### 9.1 `project.yml` 示例与 loader 的 env var 语义可能不一致

部分 example 使用 `${OPENAI_API_KEY}`。当前 `load_project_config` 读取 `api_key` 时看起来只是字符串读取，没有明显 env interpolation。如果实际未在别处处理，这会让示例和真实行为不一致。

建议：

- 明确支持 `${VAR}` / `${VAR:-default}`。
- secret 字段进入 redaction。
- artifact 中禁止写明文 key。

### 9.2 多 provider 需要真正成为控制平面

当前 per-model provider override 只覆盖 base_url/api_key，provider_id 仍是全局 provider id。这对 provider budget 和观测不够准确。

建议：

- 每个 model entry 可以引用 provider id。
- judge/generator/scorer 单独引用 provider id。
- provider budget 以真实 provider id 计数。

### 9.3 `BenchmarkInfo.higher_is_better` 与 risk rollup 要统一

当前 `aggregate_benchmark_rows` 读取了 `higher_is_better` 但没有明显用于归一化。对于 `strongreject`、`risk_rate`、`mask_score` 这类 lower-is-better 指标，如果直接平均到 risk dashboard，语义会混乱。

建议：

- 引入 normalized safety/capability score。
- 每个 metric 明确 direction。
- risk index 使用 normalized value。
- artifact 同时保留 raw metric 和 normalized metric。

### 9.4 `Task.metadata` 和 `sample.metadata` 承载了太多隐式协议

例如 benchmark、domain、runtime_container、model_metadata、OSWorld config 等都通过 metadata 传递。短期可行，长期会影响可维护性。

建议：

- metadata 保留扩展字段。
- 核心协议迁到 typed spec。
- artifact 中区分 `user_metadata` 与 `runtime_metadata`。

### 9.5 Web UI 与 Python monitor 有重复索引逻辑

当前 Python `snowl/web/monitor.py` 和 Next.js `webui/src/server/monitor.ts` 都有 SQLite/index/event ingestion 逻辑。长期会漂移。

建议：

- 选择一个 canonical indexer。
- 或将 artifact index schema 和 ingestion tests 抽成共享 contract。
- Web UI 尽量只消费稳定 API，不重复推断 runtime 状态。

### 9.6 `webui/` 与 `snowl/_webui/` 镜像仍是漂移风险

当前文档已经明确 `webui/` 是源，`snowl/_webui/` 是 packaged mirror。下一版建议自动化镜像构建，避免人工同步。

### 9.7 Benchmark registry 内置表会限制生态

内置 registry 对官方 benchmark 很方便，但外部生态必须有 plugin discovery。否则每接一个 benchmark 都要改 core。

## 10. Dynamic Safety Wind Tunnel 的具体产品形态

建议把“风洞”定义成三种运行模式。

### 10.1 Replay Mode：复现静态基准

作用：

- 跑官方 benchmark。
- 产生可比结果。
- 与论文/社区基准对齐。

对应当前 Snowl 能力最强，主要需要统一 contract 和扩展 benchmark。

### 10.2 Generate Mode：动态生成测试

作用：

- 根据风险目标生成新样本。
- 解决测试集老化。
- 自动构造环境。
- 发现未知失败模式。

命令示例：

```bash
snowl generate project.yml --suite agentic_safety --max-cases 100
snowl eval project.yml --task-source generated
```

或：

```bash
snowl eval project.yml --generate
```

### 10.3 Red-Team Loop Mode：闭环探索

作用：

- 先跑一批。
- 聚类失败和边界样本。
- 生成器根据结果继续探索。
- 把高价值样本沉淀到 casebank。

流程：

```text
seed -> generate -> run -> score -> analyze -> mutate -> run -> review -> regression
```

这是最能体现“风洞”的形态。

## 11. 面向开源用户的易用性设计

### 11.1 三分钟接入自研 agent

必须提供低门槛路径：

```bash
snowl init agent-http
snowl eval project.yml
```

HTTP 协议示例：

```json
{
  "input": {"messages": [...]},
  "tools": [...],
  "environment": {...}
}
```

返回：

```json
{
  "messages": [...],
  "actions": [...],
  "final_output": "...",
  "usage": {...},
  "trace": {...}
}
```

用户不应一开始就学习 `AgentState`、`AgentContext`、`ToolSpec` 的全部内部细节。

### 11.2 Benchmark 作者体验

提供：

- `snowl create benchmark mybench`
- adapter template。
- scorer template。
- metadata validator。
- sample preview validator。
- conformance command。

### 11.3 Generator 作者体验

提供：

- `snowl create generator mygen`
- recipe schema。
- local dry-run。
- dedup report。
- case preview。
- publish to casebank。

### 11.4 环境作者体验

提供：

- `snowl create environment webapp`
- blueprint template。
- readiness probe。
- action/observation validator。
- cleanup leak detector。

## 12. 风险、安全与治理

Snowl 面向安全测试，本身也要安全。

### 12.1 Secret 管理

需要：

- env interpolation。
- secret redaction。
- artifact secret scan。
- provider key 不进入 event/model_io。
- UI 自动隐藏 sensitive fields。

### 12.2 Sandbox 安全

需要：

- 默认网络隔离策略。
- 明确 egress allowlist。
- 文件系统 mount 最小化。
- container privileged/KVM 权限显式声明。
- malicious benchmark 防护说明。

### 12.3 生成内容安全

动态安全测试会生成敏感样本。需要：

- risk classification。
- export policy。
- private/public suite 分层。
- 审核状态。
- watermark/lineage。
- 禁止意外发布 private generated cases。

### 12.4 可复现与审计

每次运行应记录：

- Snowl version。
- plugin versions。
- benchmark versions。
- generator versions。
- provider/model versions。
- env blueprint hash。
- container image digest。
- seed。
- scorer rubric hash。

## 13. 成功指标

建议用可测指标约束下一版，而不只是功能清单。

### 13.1 接入效率

- 新 HTTP agent 接入时间 < 10 分钟。
- 新 LangGraph agent 接入代码 < 30 行。
- 新 benchmark adapter 最小实现 < 150 行。
- 新 generated suite 可通过 CLI 创建和复现。

### 13.2 执行可靠性

- container leak 率接近 0。
- provider wait 可观测。
- phase failure 可分类。
- retry 后 artifact 不破坏。
- 运行中断后可恢复。

### 13.3 扩展性

- 外部 benchmark 通过 plugin 安装，无需改 core。
- 同一实验可包含多个 benchmark/task source。
- 同一实验可包含多个 agent framework。
- 支持至少 terminal/web/desktop/mobile 四类环境 contract。

### 13.4 评测质量

- 每个 trial 有完整 evidence。
- 每个 generated case 有 lineage。
- risk dashboard 使用 normalized metrics。
- 失败样本可沉淀为 regression suite。
- case dedup/novelty 可报告。

## 14. 推荐优先级

如果资源有限，建议按以下顺序推进：

1. 先拆 `eval.py` 的控制平面职责，建立 EvalSpec、ArtifactStore、EventBus、RecoveryManager。
2. 做多 provider 和 Agent Adapter SDK，因为这直接解决自研智能体难接入。
3. 做 Environment Blueprint，把 TerminalBench/OSWorld 迁进去，同时新增 Web provider。
4. 做 EvidenceBundle 和 ScorerSuite，保证安全评测可信。
5. 做 Dynamic TestGenerator 和 CaseBank，形成风洞差异化能力。
6. 做 phase-aware scheduler，提升大规模运行体验。
7. 做 plugin ecosystem 和 benchmark conformance，支撑开源扩展。

## 15. 以好用和可扩展为核心的项目设计重构

前面的章节较多围绕目标能力展开。更关键的是：即使不考虑“动态安全风洞”这个外部表述，只从 Snowl 当前项目设计本身看，它下一版也应该围绕“好用”和“可扩展”重构。

这里的“好用”不是 UI 漂亮，也不是命令多，而是用户从想评测到拿到可信结果之间的路径足够短、错误足够可解释、产物足够可复现。

这里的“可扩展”也不是到处加 hook，而是让外部 agent、benchmark、environment、scorer、generator 的作者知道该实现哪个小接口，能用 conformance test 验证自己，没有必要改 Snowl core。

### 15.1 当前 Snowl 的真实用户路径

从代码和测试看，当前 Snowl 实际有四类用户路径。

第一类是“我要跑一个已有 benchmark”。
现在路径大致是：准备 example project，配置 provider，运行 `snowl eval` 或 `snowl bench run`。这个路径已经可用，但仍有摩擦：

- 用户必须理解 `project.yml`、`agent.py`、`scorer.py` 的关系。
- 很多 benchmark 需要 reference repo，失败时不一定能被 `snowl doctor` 级别地解释。
- `bench run` 和 `eval` 的边界对新用户不明显。
- 一个 benchmark 的 adapter 参数、project 配置、runtime 配置分散在不同层。

第二类是“我要接入自己的 agent”。
现在最自然的方式是写一个符合 `Agent.run(state, context, tools)` 的 Python 对象。这对框架作者清晰，但对外部用户偏底层：

- 用户要知道 `AgentState.output` 的 shape。
- 用户要知道 `StopReason`。
- 用户要知道 trace、usage、message 如何写。
- 如果 agent 是 HTTP 服务、LangGraph、Nexau、OpenAI SDK、CLI 程序，就需要额外胶水代码。

第三类是“我要接入一个新 benchmark”。
现在需要 subclass `BaseBenchmarkAdapter`、加 registry entry、写 scorer/example/tests/docs。这条路径是工程上正确的，但还不是开源生态友好：

- 必须改 `snowl/benchmarks/registry.py`。
- metadata、sample preview、trial metadata 的契约还不够工具化。
- 没有 `snowl create benchmark` 模板。
- conformance 目前更多是内部测试能力，而不是 benchmark 作者的开发体验。

第四类是“我要调试一次失败运行”。
现在有 `.snowl/runs`、events、diagnostics、Web monitor。这是强项。但用户仍可能遇到：

- 不知道失败是 agent、provider、container、scorer、环境 readiness 还是 Snowl 调度问题。
- 证据散落在 payload/trace/events/diagnostics/log 中。
- rerun/retry 有，但还不是按 phase 和 failure class 引导。
- UI 能显示结果，但还不够像“下一步该做什么”的操作台。

因此，下一版设计的第一原则应该是：每条用户路径都有清晰的最短路径、渐进式进阶路径、可验证的 conformance、可解释的失败诊断。

### 15.2 保留一个小内核，扩展都走边界

Snowl 当前容易扩大的地方很多：benchmark、agent、model provider、environment、scorer、UI、scheduler、generator。如果这些都直接互相引用，项目会越来越难改。

建议把 Snowl 内核定义得非常小：

```text
Snowl Core Kernel =
  EvalSpec
  Subject/Agent contract
  TaskSource/Scenario/Sample contract
  Environment contract
  Scorer contract
  TrialPlan/TrialOutcome contract
  Event/Evidence/Artifact contract
```

内核只定义数据模型和协议，不知道 StrongReject、TerminalBench、OSWorld、LangGraph、Nexau、Playwright、Android emulator 的细节。

所有具体实现都走扩展边界：

- benchmark 是插件。
- agent framework 是 adapter。
- environment 是 provider。
- model provider 是 provider。
- scorer 是 scorer plugin。
- generator 是 generator plugin。
- UI 是 artifact/event 的消费者。

这会让项目从“中心不断长 if/else”变成“内核稳定，边缘扩展”。

### 15.3 把扩展点分成五个，不要混成一个 plugin 万能口

开源框架常见问题是“plugin”太泛，最后每个 plugin 都能改一切。Snowl 应该把扩展点拆清楚。

1. `AgentAdapter`
   解决待测目标怎么接入。

2. `TaskSource` / `BenchmarkAdapter` / `TestGenerator`
   解决测试任务从哪里来。

3. `EnvironmentProvider`
   解决任务在哪个环境跑。

4. `Scorer` / `ScorerSuite`
   解决如何评价。

5. `Reporter` / `ArtifactConsumer`
   解决如何展示、导出、分析。

这五类扩展有不同生命周期和风险等级，不应共享一个过宽接口。

### 15.4 当前核心契约的改造建议

#### Task：从“可迭代样本容器”升级为“任务语义声明”

当前：

```python
Task(task_id, env_spec, sample_iter_factory, metadata)
```

这个设计非常轻，但 `metadata` 压力过大。建议保留兼容，同时内部升级：

```text
TaskDefinition
  task_id
  objective
  input_schema
  expected_capabilities
  default_environment
  metadata

Sample
  sample_id
  input
  labels
  scenario_ref
  environment_overrides
  metadata
```

对用户而言仍可以写简单 `Task`；对平台而言，scenario/environment/labels 不再都塞进 metadata。

#### Agent：从“必须实现 Snowl Python 协议”变成“多 adapter 统一成 Subject”

当前 `Agent.run` 是好内核，但不是好入口。建议：

- 内核继续保留 `Agent.run`。
- 用户入口新增 `subjects:`。
- 所有外部框架通过 adapter 转成内部 `Agent` 或 `SubjectHandle`。
- 对 Python 高级用户，仍允许直接写原生 `Agent`。

也就是说，`Agent.run` 变成 adapter 作者使用的低层协议，而不是所有用户必须学习的第一入口。

#### Scorer：从“一个 scorer 文件”升级为“评分套件”

当前 scorer contract 很清晰，但评测真实需求更像 pipeline。建议：

- 保留单 scorer 最短路径。
- 内部统一为 `ScorerSuite`，哪怕只有一个 scorer。
- scoring artifact 记录 scorer id、rubric version、inputs、evidence refs。

#### EnvSpec：从 env_type/provided_ops 升级为 EnvironmentBlueprint

当前 `EnvSpec` 可以做 capability compatibility 检查，这是好设计。但对于 Web/Mobile/PC 环境，`env_type` 太粗，`provided_ops` 太弱。

建议：

- `EnvSpec` 保留为兼容层。
- 新增 `EnvironmentBlueprint` 表达 provider、image/device/app、reset、observation、resources、安全策略。
- `provided_ops` 作为 blueprint 的 action capability projection。

### 15.5 “好用”的 API 设计：三层入口

Snowl 应该同时服务新手、普通工程用户和高级扩展作者。建议提供三层入口。

#### 第一层：零代码/少代码

面向“我只想评测一个模型/agent”。

```bash
snowl init
snowl bench list
snowl eval project.yml
snowl web
```

配置尽量声明式：

```yaml
subjects:
  my_model:
    adapter: openai_compatible_chat
    provider: siliconflow
    model: Qwen/Qwen3-32B
```

不需要写 `agent.py`。

#### 第二层：低代码

面向“我有自己的 agent 服务/graph”。

```yaml
subjects:
  my_agent:
    adapter: http
    endpoint: http://localhost:9000/snowl
```

或者：

```yaml
subjects:
  my_graph:
    adapter: langgraph
    module: ./graph.py
    factory: build_graph
```

用户只实现一个小协议。

#### 第三层：全代码扩展

面向 benchmark、environment、generator、scorer 作者：

```bash
snowl create benchmark mybench
snowl create adapter myframework
snowl create environment myenv
snowl create generator mygen
snowl plugin test .
```

这一层需要完整 contract，但必须配模板和 conformance。

### 15.6 “可扩展”的工程边界：从当前函数切分

不需要凭空设计，可以直接沿当前 `eval.py` 的自然边界切。

当前 `_discover_tasks/_discover_agents/_discover_scorers/_discover_tools` 应成为：

```text
snowl.discovery.ComponentLoader
```

当前 `_build_plan`、`_trial_key` 应成为：

```text
snowl.planning.PlanBuilder
snowl.planning.TrialIdentity
```

当前 `_resolve_runtime_budgets` 应成为：

```text
snowl.runtime.RuntimePolicy
```

当前 `_LiveEventsWriter`、`_enrich_event_row`、`_derive_pretask_events` 应成为：

```text
snowl.observability.EventBus
snowl.observability.EventNormalizer
```

当前 `_bootstrap_recovery_state`、`_record_recovery_attempt`、`_schedule_auto_retry` 相关逻辑应成为：

```text
snowl.runtime.RecoveryManager
```

当前 `_write_artifacts` 应拆成：

```text
snowl.artifacts.RunArtifactStore
snowl.aggregator.RollupBuilder
snowl.reports.StaticHtmlReport
```

当前 `_run_one` 应成为：

```text
snowl.runtime.TrialRunner
```

当前 while loop dispatch 应成为：

```text
snowl.runtime.RunScheduler
```

这样做的好处是，重构不是抽象洁癖，而是把已经存在的职责边界显式化。每一步都能用现有测试验证。

### 15.7 设计一个“先 plan 再 run”的体验

好用的评测框架必须让用户在烧钱、起容器、启动模拟器之前知道将要发生什么。

建议新增：

```bash
snowl plan project.yml
```

输出：

- 将运行哪些 subjects。
- 将运行哪些 benchmarks/task sources。
- 将生成多少 cases。
- 需要哪些 environments。
- 预计多少 provider calls。
- 预计多少 judge calls。
- 预计多少 container/browser/mobile slots。
- 哪些配置缺失。
- 哪些 secret 未设置。
- 哪些 reference repo 缺失。
- 哪些 benchmark conformance 未通过。

当前 `plan.json` 是运行 artifact。下一版要把 plan 提前暴露为用户决策工具。

### 15.8 设计一个 `snowl doctor`

很多“难用”不是核心能力差，而是失败解释差。Snowl 尤其依赖 Docker、Node、reference repos、API keys、model providers、browser/mobile runtimes。

建议：

```bash
snowl doctor project.yml
```

检查：

- Python package 是否安装。
- Web UI 是否可构建。
- provider secret 是否存在但不打印。
- reference repo 是否存在。
- Docker/Compose 是否可用。
- KVM/虚拟化能力。
- Playwright 浏览器是否安装。
- Android emulator/Appium 是否可用。
- benchmark dataset path 是否有效。
- scorer judge provider 是否配置。
- artifact 目录是否可写。

这比在 trial 运行中失败要友好得多。

### 15.9 错误模型要成为框架契约

当前已经有 `_classify_failure_from_serialized`，这是好苗头。下一版应把 failure taxonomy 升级为正式 contract。

建议统一错误分类：

```text
config.invalid
dependency.missing
provider.auth
provider.rate_limit
provider.timeout
environment.prepare
environment.readiness
environment.action
agent.protocol
agent.runtime
scorer.runtime
scorer.disagreement
scheduler.cancelled
artifact.write
semantic.failure
```

每个错误包含：

- retryable。
- failed_phase。
- suggested_action。
- evidence_refs。
- responsible_component。

Web UI 和 CLI 都能基于它给出下一步动作。

### 15.10 不要让 YAML 变成新的复杂性中心

`project.yml` 是好入口，但不能把所有复杂度都推给 YAML。好用的原则是：

- 简单任务有短配置。
- 复杂任务可以展开。
- 默认值可解释。
- `snowl plan` 能显示展开后的 lock spec。
- 高级字段有 schema 和 autocomplete。

建议生成：

```text
eval_spec.lock.json
```

这份 lock 文件记录所有默认值、插件解析、provider 展开、benchmark 版本、generator recipe、environment hash。用户写的是简洁 YAML，Snowl 运行的是完整 lock spec。

### 15.11 插件作者需要“窄接口 + 强测试”

对开源扩展而言，最重要的是：

- 我该实现什么？
- 我实现得对不对？
- 我升级 Snowl 后会不会坏？

因此每个扩展点都应有 conformance：

```bash
snowl conformance agent-adapter ./my_adapter
snowl conformance benchmark mybench
snowl conformance environment ./my_env
snowl conformance scorer ./my_scorer
snowl conformance generator ./my_generator
```

conformance 应检查：

- schema。
- sample identity 稳定性。
- deterministic ordering。
- artifact safety。
- event shape。
- cleanup 行为。
- retry/cancel 行为。

这比文档更能保证可扩展。

### 15.12 Web UI 应围绕任务流，而不是 artifact 文件

当前 UI 消费 artifact，这很好。但产品体验上，用户关心的是任务流：

1. 我这次评测覆盖了什么？
2. 哪些模型/agent 风险最高？
3. 哪些失败是真的安全问题？
4. 哪些失败是环境/调度问题？
5. 我能否复现某个 trial？
6. 我能否把某个失败样本加入 regression？
7. 我能否比较两个实验？

所以 UI 信息架构应从 artifact 名称转为 workflow：

- Overview：风险和进度。
- Plan：本次计划和资源。
- Runs：执行监控。
- Trials：失败 triage。
- Evidence：证据查看。
- Cases：样本治理。
- Compare：实验对比。
- Resources：环境和 provider 资源。

Artifact 仍是后端契约，但不应该成为用户理解系统的前置知识。

### 15.13 当前测试体系也可以成为重构护栏

现有 tests 已经覆盖很多设计意图：

- decorator discovery。
- task/agent/scorer contracts。
- benchmark registry。
- eval planning。
- runtime engine。
- resource scheduler。
- web monitor。
- benchmark metadata。
- risk rollups。

下一版重构不应先删改这些测试，而应把它们当成“行为锁”。每抽出一个模块，先保持这些测试不变；等新 contract 成熟后，再新增 v2 tests。

推荐新增测试类别：

- `tests/test_eval_spec_v2.py`
- `tests/test_agent_adapter_conformance.py`
- `tests/test_environment_blueprint.py`
- `tests/test_generator_lineage.py`
- `tests/test_evidence_bundle.py`
- `tests/test_phase_scheduler.py`
- `tests/test_plugin_discovery.py`
- `tests/test_doctor.py`

### 15.14 不该做的设计

为了可扩展，以下方向应避免。

不要把动态生成写进某几个 benchmark adapter。
生成是平台能力，benchmark adapter 只是 seed/source 之一。

不要让 agent adapter 直接操作 container lifecycle。
环境归 runtime/environment provider 管，agent 只消费 observation/tool/action。

不要把 Web/Mobile/Desktop 都塞进 `runtime_container`。
容器只是环境实现方式之一，不能成为环境抽象本身。

不要让 frontend hardcode benchmark 语义。
benchmark/domain/metric/preview 都应来自 backend metadata。

不要让 scorer 隐式读取任意文件来找证据。
证据应该通过 EvidenceBundle refs 显式传递。

不要过早分布式化。
先把本地 phase/resource/artifact contract 做稳，分布式只是执行后端替换。

不要为了“强大”牺牲最短路径。
`snowl eval project.yml` 必须继续简单。

### 15.15 一句话设计标准

之后判断每个重构是否值得，可以用这几个问题：

- 新用户能不能更快跑起来？
- 自研 agent 能不能少写 glue code？
- 新 benchmark 能不能不改 core？
- 新环境能不能不污染 runtime 主流程？
- 失败能不能更快定位责任组件？
- 运行结果能不能更可靠复现？
- UI 能不能引导下一步，而不是只展示文件？
- 内核 contract 是否更小、更稳定？

如果答案是否定的，那这个设计大概率只是增加复杂度，不是提升好用和可扩展。

## 16. 总结判断

Snowl 当前最有价值的资产不是某个 benchmark adapter，而是已经形成的四个基础：

- `Task x AgentVariant x Sample` 的执行单元。
- YAML-first 的可复现实验入口。
- provider/container/scoring 分离的调度意识。
- artifact + event + Web monitor 的观测链路。

下一版要避免把“动态安全测试风洞”做成一堆新 benchmark 和脚本。真正应该重构出来的是：

- 面向多框架待测 agent 的 adapter 层。
- 面向静态与动态任务的 task source/generator 层。
- 面向 PC/Mobile/Terminal/Web 的 environment blueprint 层。
- 面向证据、评分、风险聚合的 evaluation layer。
- 面向大规模可靠运行的 phase-aware runtime control plane。
- 面向开源生态的 plugin/conformance layer。

如果这些层次成立，Snowl 才能同时解决：

- 基准测试不统一：通过统一 TaskSource、BenchmarkInfo、ScorerSuite、normalized rollup。
- 自研智能体难接入：通过 Agent Adapter SDK 和标准 HTTP/process 协议。
- 测试集易老化：通过 TestGenerator、CaseBank、lineage、dedup、regression loop。
- 多环境评测割裂：通过 EnvironmentBlueprint 与统一 action/observation/evidence。
- 大规模运行不可靠：通过 phase-aware scheduler、resource model、recovery 和 observability。

这条路线既保留当前 Snowl 已经做对的东西，也把未来最关键的产品能力放在可扩展的平台抽象上。
