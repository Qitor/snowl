# Snowl（中文说明）

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl 是一个通用的 Agent 评测框架，核心使用范式非常简单：

- 定义 `Task`
- 定义 `Agent`
- 定义 `Scorer`
- 一条命令运行：`snowl eval ...`

框架目标是让你把精力放在“评测对象与评测规则”上，而不是运行编排细节（尤其是容器、环境、并发、日志与产物管理）。

## 命名由来

`snowl` 来自 **Snow Owl（雪鸮）**。

我们选择这个名字，是希望传达：

- 在复杂环境中进行敏锐观测和信号识别
- 在高复杂度评测链路中保持稳定、冷静和可靠
- 与 Agent 安全 / AI 安全评测场景具有很强语义贴合度

## 一、项目能做什么

- 统一的评测契约，覆盖 QA / Terminal / GUI 等不同类型任务
- `Task` 和 `Agent` 都是一等评测对象
- 多指标评分（含 model-as-judge）
- 内置 benchmark 适配器：`strongreject`、`terminalbench`、`osworld`、`toolemu`、`agentsafetybench`
- 研究友好的产物导出：`trials.jsonl`、`events.jsonl`、`metrics_wide.csv`
- Live CLI（交互式实时界面）

## CLI 界面预览

![Snowl CLI Agent View](./assets/cli_agent.png)
![Snowl CLI Model View](./assets/cli_model.png)

## 核心 Roadmap

1. 适配更多 benchmark：扩展更多主流评测集的一方适配器。
2. 提升 runtime/engine 并发性能：优化调度、并行度与整体吞吐能力。
3. 完成 Web UI：提供完整的网页端运行监控、结果下钻与对比分析体验。
4. 适配更多 agent framework：增加更多外部 agent 生态的接入路径。
5. 加入更多 built-in 测评工具包：补充通用 scorer/tool 组合能力，降低评测搭建成本。

## 二、本地部署与运行（推荐流程）

## 1) 环境要求

- Python >= 3.10
- macOS / Linux（容器类 benchmark 需要本机可用 Docker）

可选但常用：

- Docker Desktop（用于 terminalbench / osworld 的容器链路）

## 2) 准备 benchmark 参考仓库（必做）

Snowl 默认按固定目录读取 benchmark 数据与任务定义，请把仓库 clone 到：

- `references/terminal-bench`
- `references/OSWorld`
- `references/strongreject`
- `references/ToolEmu`
- `references/Agent-SafetyBench`


在项目根目录执行：

```bash
cd /Users/morinop/coding/snowl_v2
git clone <TERMINAL_BENCH_GIT_URL> references/terminal-bench
git clone <OSWORLD_GIT_URL> references/OSWorld
git clone <STRONGREJECT_GIT_URL> references/strongreject
git clone <TOOLEMU_GIT_URL> references/ToolEmu
git clone <AGENT_SAFETY_BENCH_GIT_URL> references/Agent-SafetyBench
```

如果你们团队使用内部镜像地址，替换 URL 即可，但目标目录名必须保持不变。

## 3) 使用 conda 创建环境并安装

在项目根目录执行：

```bash
cd /Users/morinop/coding/snowl_v2
conda create -n snowl python=3.11 -y
conda activate snowl
pip install -U pip
pip install -e .
```

验证 CLI 是否可用：

```bash
snowl --help
```

如果不走安装，也可以：

```bash
python -m snowl.cli --help
```

## 3.1) PyPI 打包与发布

本项目已经按 PyPI 包 `snowl` 的方式配置。

本地构建与校验：

```bash
cd /Users/morinop/coding/snowl_v2
./scripts/release_pypi.sh
```

完整发布说明见：

- `/Users/morinop/coding/snowl_v2/docs/pypi_release.md`

## 4) 模型配置（OpenAI-Compatible）

可以用环境变量，也可以在 example 目录放 `model.yml`。

示例 `model.yml`：

```yaml
openai_compatible:
  base_url: https://api.siliconflow.cn/v1
  api_key: sk-...
  model: Qwen/Qwen3-32B
  timeout: 30
  max_retries: 2
```

优先级：

1. 环境变量（`OPENAI_*`）
2. `model.yml` / `model.yaml`

也就是说：环境变量可以覆盖 `model.yml`。

## 5) 快速跑通

### 方式 A：直接跑 example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/toolemu-official
```

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/agentsafetybench-official
```

### 方式 B：通过 benchmark 适配器跑

先看支持哪些 benchmark：

```bash
snowl bench list
```

以 terminalbench 为例：

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official \
  --split test
```

## 一个文件夹一键评测（核心使用方式）

Snowl 的核心 UX 是：把你要评测的对象放进一个目录，直接 `snowl eval <目录>`。

推荐最小目录结构：

```text
my-eval/
  task.py
  agent.py
  scorer.py
  model.yml        # 可选
  tool.py          # 可选
  panels.yml       # 可选（自定义 UI 面板）
```

运行：

```bash
snowl eval /absolute/path/to/my-eval
```

Snowl 自动发现规则：

- `task.py` 导出一个或多个 `Task`（对象或工厂）
- `agent.py` 导出一个或多个 `Agent` / `AgentVariant`（对象或工厂）
- `scorer.py` 导出 scorer（对象或工厂）
- `tool.py` 可选，`@tool` 定义的工具会自动注册

如果是 benchmark 模式：

- benchmark adapter 负责把 benchmark 数据加载为 `Task`
- 你的目录继续提供 `agent/scorer/tool`
- 使用 `snowl bench run <benchmark> --project <你的目录> ...`

## 自动矩阵展开（核心评测思想）

Snowl 的核心设计之一是把评测自动展开成矩阵执行，而不是让用户手写调度脚本。

目标态矩阵：

- `Task x AgentVariant x Scorer x Sample`

当前实现状态：

- 已自动展开：`Task x AgentVariant x Sample`
- scorer 执行：单次 run 只激活一个 scorer（当前为发现到的第一个 scorer）
- 单次 run 多指标：支持（一个 scorer 返回多个 metric）

当前推荐实践：

1. 在 `agent.py` 定义多个 agent/variant，让 Snowl 自动做对比展开。
2. 在一个 scorer 中返回多指标（例如 `accuracy`、`safety`、`latency_score`）。
3. 如果当前就要做“多 scorer 严格隔离对比”，可以先分多次 run 执行（按 scorer 组织目录或导出约定）。

路线方向（roadmap）：

- 支持一等公民的 `Task x AgentVariant x Scorer` 自动展开，在一次编排中对比多个 scorer。

当前 plan 模式示例：

- `1 Task x 1 AgentVariant` -> single
- `N Task x 1 AgentVariant` -> task_sweep
- `1 Task x M AgentVariant` -> compare
- `N Task x M AgentVariant` -> matrix

## Decorator 机制与设计想法

Snowl 支持两种发现方式：

1. 装饰器优先（推荐）
2. fallback 对象扫描（兼容旧写法）

推荐写法：

```python
from snowl.core import task, agent, scorer, Task, EnvSpec, Score

@task(task_id="demo:test")
def build_task():
    return Task(
        task_id="demo:test",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([{"id": "s1", "input": "hello"}]),
    )

@agent(agent_id="demo_agent")
class DemoAgent:
    async def run(self, state, context, tools=None):
        state.output = {"message": {"role": "assistant", "content": "ok"}}
        return state

@scorer(scorer_id="demo_scorer")
class DemoScorer:
    def score(self, task_result, trace, context):
        return {"pass": Score(value=1.0)}
```

为什么推荐 decorator：

- 身份显式化：`task_id/agent_id/scorer_id` 更清晰
- 自动发现顺序稳定，减少“同名冲突/隐式行为”
- example 和 benchmark 迁移代码更短、更易读
- 代码评审时更容易理解“哪些对象会被运行系统拾取”

## Runtime / Env / Tool 设计原理

Snowl 的关键设计是把“评测编排”和“环境复杂性”解耦。

核心原则：

1. 用稳定契约组织系统：`Task + Agent + Scorer`。
2. `TaskResult` 保持“固定核心字段 + 可扩展 payload”。
3. 工具与环境显式对接：`required_ops` vs `provided_ops`。
4. 容器/沙箱等重逻辑集中在 runtime/env 层，而不是散落在用户任务代码中。

`EnvSpec` 的意义：

- `env_type`：任务运行域（`local`、`terminal`、`gui` ...）
- `provided_ops`：该环境可提供的操作能力
- `sandbox_spec`（可选）：声明容器/沙箱需求

安全前置校验：

- 如果 Tool 需要的 ops 超出 Env 提供能力，trial 在执行前就会 fail-fast，并给出明确报错

Runtime 分层：

- `eval.py`：计划生成与整体编排
- `runtime/engine.py`：单 trial 执行
- `runtime/container_runtime.py`：容器生命周期（build/up/down）与事件上报
- `envs/`：具体执行器（terminal/gui/sandbox）

这套分层的价值：

- benchmark 适配者可以专注 task 加载和 scorer 语义
- agent 作者可以专注 agent 行为，不用重复造容器管理轮子
- 维护者可在 runtime 层统一优化并发、稳定性、日志、诊断能力

## 设计原则（维护共识）

1. 默认简单：用户定义好 `task.py + agent.py + scorer.py` 就能跑。
2. 高级能力可选：并发、过滤、UI、重跑策略通过 CLI 参数叠加，不强迫配置化。
3. benchmark 视为 TaskProvider：benchmark 不是 runtime 中心，任务契约才是中心。
4. 不追求 100% 上游实现复刻：优先保证任务加载语义和评分语义一致。
5. 观测优先：所有长流程都应该有事件流和落盘日志，便于复现与定位。
6. 产物面向研究：结果必须可机器分析（jsonl/csv/diagnostics）。

## 三、核心命令

- `snowl eval <path>`
  - 自动发现 `task.py` / `agent.py` / `scorer.py` / `tool.py` 并运行
- `snowl bench run <benchmark> --project <example_dir>`
  - 用 benchmark adapter 加载任务，用本地 agent/scorer 执行
- `snowl bench list`
  - 列出内置 benchmark adapter
- `snowl bench check <benchmark>`
  - 跑 adapter 一致性检查
- `snowl examples check [examples_dir]`
  - 检查 examples 布局规范

常用参数：

- 过滤：`--task`、`--agent`、`--variant`
- 并发：`--max-trials`、`--max-sandboxes`、`--max-builds`、`--max-model-calls`
- 可靠性：`--resume`、`--rerun-failed-only`
- UI：`--no-ui`、`--ui-mode`、`--ui-theme`、`--ui-refresh-profile`
  主题值：`contrast`、`quiet`、`research`、`research_redops`

示例（即使是非 docker 任务也强制使用红色系主题）：

```bash
snowl eval /absolute/path/to/my-eval --ui-theme research_redops
```

## 四、项目架构（维护视角）

Snowl 的执行单元是 `Task x AgentVariant x Sample`。

```text
                         +----------------------+
task.py ---------------->|                      |
agent.py --------------->|      Eval Planner    |
scorer.py -------------->|                      |
tool.py (optional) ----->|                      |
                         +----------+-----------+
                                    |
                                    v
                         +----------+-----------+
                         |      Runtime Engine  |
                         +----+-----+-----+-----+
                              |     |     |
                              |     |     +------------------------+
                              |     |                              |
                              v     v                              v
                  +-----------+--+  +-------------+     +----------+-----------+
                  |ContainerRuntime| |SandboxRuntime|    |      Agent.run      |
                  +-----------+--+  +-------------+     +----------+-----------+
                                                                  |        |
                                                                  v        v
                                                         +--------+--+  +--+------+
                                                         |Model Client|  | Tools  |
                                                         +-----------+  +---------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |  TaskResult+Trace  |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |    Scorer.score    |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |       Metrics      |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         |      Aggregator    |
                                                         +--------+-----------+
                                                                  |
                                                                  v
                                                         +--------+-----------+
                                                         | Artifacts + Live UI|
                                                         +--------------------+
```

模块职责图：

- `snowl/core/`
  - 数据契约与协议：`Task`、`Agent`、`Scorer`、`ToolSpec`、`EnvSpec`、`TaskResult`
  - 装饰器：`@task`、`@agent`、`@scorer`、`@tool`
- `snowl/eval.py`
  - 自动发现、计划生成、运行编排、checkpoint/resume、产物写入
- `snowl/runtime/`
  - trial engine 与 `ContainerRuntime`
- `snowl/envs/`
  - `TerminalEnv` / `GuiEnv` / sandbox runtime
- `snowl/model/`
  - OpenAI-compatible client，含重试、超时、错误格式化
- `snowl/scorer/`
  - 共性 scorer 能力（text/model judge/composition/unit-test）
- `snowl/benchmarks/`
  - benchmark adapter 与注册表
- `snowl/ui/`
  - Live CLI 渲染、交互、panel 系统
- `snowl/aggregator/`
  - 聚合与 schema 元信息

## 五、运行产物与日志

每次运行会在：

- `<project>/.snowl/runs/<timestamp>/`
- `<project>/.snowl/runs/by_run_id/run-...`（映射到实际目录）

关键文件：

- `run.log`：完整运行日志（实时 append）
- `plan.json`、`summary.json`、`aggregate.json`、`outcomes.json`
- `trials.jsonl`：逐 trial 结果
- `events.jsonl`：事件流
- `metrics_wide.csv`：宽表指标（便于分析）
- `diagnostics/*.json` + `diagnostics_index.json`
- `report.html`

### 实时日志与可观测性（包含模型完整 I/O）

Snowl 现在会把 **运行时事件 + 模型完整输入输出** 按可回放格式落盘：

- `run.log`：运行开始即创建，并实时 append。
- `events.jsonl`：结构化事件流，便于机器分析。
- `trials.jsonl`：每个 trial 的最终结果行。

核心事件（建议重点关注）：

- `runtime.agent.step`：agent 每一步执行进度
- `runtime.model.query.start|finish|error`：模型调用生命周期
- `runtime.model.io`：OpenAI-compatible 完整请求/响应
  - 请求包含完整 `messages` 与 generation kwargs
  - 响应包含 `message`、`raw` JSON、`usage`、`timing`
- `runtime.env.command.start|stdout|stderr|finish|timeout`：容器/环境命令流

常用排障命令：

```bash
# 通过 run_id 快速定位目录
ls -la <project>/.snowl/runs/by_run_id/

# 实时跟踪运行日志
tail -f <project>/.snowl/runs/by_run_id/run-.../run.log

# 只看模型 I/O 与模型报错
rg "runtime.model.io|runtime.model.query.error" \
  <project>/.snowl/runs/by_run_id/run-.../run.log
```

## 六、如何新增功能（给维护同学）

## 1) 新增 Agent

```python
from snowl.core import agent

@agent(agent_id="my_agent")
class MyAgent:
    async def run(self, state, context, tools=None):
        ...
        return state
```

## 2) 新增 Task

```python
from snowl.core import Task, EnvSpec, task

@task(task_id="my_task:test")
def build_task():
    return Task(
        task_id="my_task:test",
        env_spec=EnvSpec(env_type="local"),
        sample_iter_factory=lambda: iter([{"id": "s1", "input": "hello"}]),
        metadata={"benchmark": "my_task"},
    )
```

## 3) 新增 Scorer

```python
from snowl.core import scorer, Score

@scorer(scorer_id="my_scorer")
class MyScorer:
    def score(self, task_result, trace, context):
        return {"accuracy": Score(value=1.0)}
```

## 4) 新增 Tool（自动生成 ToolSpec）

```python
from snowl.core import tool

@tool(required_ops=("terminal.exec",))
def run_cmd(cmd: str) -> str:
    """Run shell command.

    Args:
      cmd: Command to execute.
    """
    ...
```

## 5) 新增 Benchmark Adapter

在 `snowl/benchmarks/<name>/adapter.py` 实现：

- `info`
- `list_splits()`
- `load_tasks(split, limit, filters) -> list[Task]`

然后在 `snowl/benchmarks/registry.py` 注册。

建议原则：

- benchmark 特有逻辑尽量留在 `snowl/benchmarks/<name>/`
- 共性 scorer 能力沉淀到 `snowl/scorer/`
- 保持事件名和产物 schema 稳定（便于下游分析）

## 七、Examples 目录约定

所有示例都在顶层 `examples/`（不是 `snowl/examples`）：

```text
examples/
  <example_name>/
    task.py
    agent.py
    scorer.py
    tool.py      # 可选
    model.yml    # 可选
```

运行：

```bash
snowl eval examples/<example_name>
```

## 八、常见问题排查

- 模型请求失败
  - 优先看 `run.log` + `events.jsonl`
  - 关注 `runtime.model.query.error` 的状态码/超时信息
- Docker 相关失败
  - 先确认 `docker compose version` 可用
  - 看 `run.log` 中 `terminalbench.container.*`、`runtime.env.command.*`
- UI 看不到细节
  - 尝试 `--ui-mode ops_dense`
  - 或 `--no-ui` 先看纯日志跑通链路

## 九、相关设计文档

- `DESIGN.md`
- `task_p0.md`
- `task_p1.md`
- `todo_list.md`
- `todo_list_p1.md`
- `ui_tasks.md`
- `ux_next.md`

---

如果你是新加入维护的同学，推荐阅读顺序：

1. `snowl/cli.py`
2. `snowl/eval.py`
3. `snowl/runtime/engine.py` + `snowl/runtime/container_runtime.py`
4. 任意一个 benchmark adapter（建议先看 `terminalbench`）
5. 对应 example（`examples/terminalbench-official/`）

这条路径可以最快建立端到端心智模型。
