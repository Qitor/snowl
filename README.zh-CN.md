# Snowl（中文说明）

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl 是一个 Agent 评测框架，并且正在朝“工业级评测平台”演进。

它的核心契约故意保持很小：

- 定义 `Task`
- 定义 `Agent`
- 定义 `Scorer`
- 用 `snowl eval ...` 运行

其余复杂度都由平台层承担：

- benchmark 适配
- 多模型展开
- runtime 编排
- container 生命周期管理
- 评分与聚合
- 产物与可观测性
- Web 运行监控

## 项目文档入口

- [START_HERE.md](./START_HERE.md)：最快速的仓库导览
- [ARCHITECTURE.md](./ARCHITECTURE.md)：当前系统架构与工业化方向
- [PLANS.md](./PLANS.md)：产品与工程路线图
- [AGENTS.md](./AGENTS.md)：给 Codex 等 coding agent 的仓库规则
- [docs/codex_best_practices.md](./docs/codex_best_practices.md)：本仓库的 Codex 使用建议

## 当前 Snowl 已经具备的能力

Snowl 现在已经不是“几个 benchmark 脚本的集合”，而是有共享平台底座的评测框架。

当前产品形态：

- 通过 `snowl eval <path>` 跑自定义评测目录
- 通过 `snowl bench run <benchmark> --project <path>` 跑 benchmark 适配器
- 通过 `model.yml` 做项目级多模型 authoring
- 内置 benchmark：
  - `strongreject`
  - `terminalbench`
  - `osworld`
  - `toolemu`
  - `agentsafetybench`
- `.snowl/runs/` 下的完整产物体系
- 基于 Next.js 的 Web monitor：run gallery、run workspace、实时日志、历史对比
- 面向 terminal / GUI benchmark 的 container-aware runtime
- resume 和 rerun-failed 能力

当前部署目标仍然是：本地单机评测，但可观测性已经比较完整。

## 快速开始

### 1. 安装

```bash
cd /Users/morinop/coding/snowl_v2
pip install -e .
```

安装阶段会一并构建内置 Web UI。

### 2. 准备 benchmark references

部分官方 example 依赖外部 benchmark 仓库，并要求固定目录名：

- `references/terminal-bench`
- `references/OSWorld`
- `references/strongreject`
- `references/ToolEmu`
- `references/Agent-SafetyBench`

示例：

```bash
cd /Users/morinop/coding/snowl_v2
git clone <TERMINAL_BENCH_GIT_URL> references/terminal-bench
git clone <OSWORLD_GIT_URL> references/OSWorld
git clone <STRONGREJECT_GIT_URL> references/strongreject
git clone <TOOLEMU_GIT_URL> references/ToolEmu
git clone <AGENT_SAFETY_BENCH_GIT_URL> references/Agent-SafetyBench
```

### 3. 跑官方 example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official
```

其他 example：

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official
snowl eval /Users/morinop/coding/snowl_v2/examples/toolemu-official
snowl eval /Users/morinop/coding/snowl_v2/examples/agentsafetybench-official
```

### 4. 通过 benchmark adapter 运行

```bash
snowl bench list
```

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official \
  --split test
```

## 默认运行体验

现在默认 CLI 行为是：

- 前台：plain terminal progress / logging，跟随评测本身
- 后台：自动拉起 Web monitor sidecar
- 可选：`--cli-ui` 打开旧的 live CLI 面板

典型命令：

```bash
snowl eval /absolute/path/to/my-eval
```

实际行为：

1. 终端先打印 run 的启动信息和进度
2. 当 run 真正初始化完成后，再打印 Web URL，比如 `http://127.0.0.1:8765`
3. 前台始终是评测任务本身
4. 停掉 eval 时，也会一起停掉这次自动拉起的 monitor sidecar

常用参数：

- 过滤：`--task`、`--agent`、`--variant`
- 并发限制：`--max-trials`、`--max-sandboxes`、`--max-builds`、`--max-model-calls`
- 可靠性：`--resume`、`--rerun-failed-only`
- monitor：`--no-web-monitor`
- 旧 live CLI：`--cli-ui`

手动 monitor 仍然可用：

```bash
snowl web monitor --project /absolute/path/to/my-eval --host 127.0.0.1 --port 8765
```

## 评测目录契约

推荐目录结构：

```text
my-eval/
  task.py
  agent.py
  scorer.py
  model.yml        # 推荐
  tool.py          # 可选
  panels.yml       # 可选
```

自动发现规则：

- `task.py`：导出一个或多个 `Task` 或工厂
- `agent.py`：导出一个或多个 `Agent` / `AgentVariant` 或工厂
- `scorer.py`：导出 scorer 或工厂
- `model.yml`：项目级 provider / 被测模型 / 可选 judge 配置
- `tool.py`：可选工具定义

然后直接运行：

```bash
snowl eval /absolute/path/to/my-eval
```

## 多模型 Authoring

Snowl 现在正式推荐项目级 model matrix。

示例 `model.yml`：

```yaml
provider:
  kind: openai_compatible
  base_url: https://api.siliconflow.cn/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: qwen25_7b
      model: Qwen/Qwen2.5-7B-Instruct
    - id: qwen3_32b
      model: Qwen/Qwen3-32B

judge:
  model: gpt-4.1-mini
```

语义：

- `provider`：这个 example 使用的唯一 provider
- `agent_matrix.models`：被测模型列表
- `judge.model`：可选的 scorer/judge 模型，和被测模型分离

`agent.py` 推荐写法：

```python
from pathlib import Path

from snowl.agents import build_model_variants
from snowl.core import agent


def build_agent_for_model(model_entry, provider_config):
    ...


@agent(agent_id="demo_agent")
def agents():
    return build_model_variants(
        base_dir=Path(__file__).parent,
        agent_id="demo_agent",
        factory=build_agent_for_model,
    )
```

现在这套模式已经同时覆盖 QA 型 example，以及 TerminalBench、OSWorld 这种 container-heavy example。

## 当前执行模型

Snowl 当前真正执行的矩阵是：

- `Task x AgentVariant x Sample`

一条 run 的主流程大致是：

1. 项目发现
2. model matrix 展开成 `AgentVariant`
3. 生成 plan
4. runtime 调度
5. trial 执行
6. scorer 打分与聚合
7. 产物落盘
8. CLI / Web 可观测性消费

当前重要限制：

- 一个 run 只有一个 active scorer
- experiment 级比较是跨多个 runs 完成的，不是单个统一的大调度器
- 当前并发能力仍然是本地单机级别

## 产物与可观测性

每次 run 的产物都在：

```text
<project>/.snowl/runs/<timestamp>/
```

关键文件：

- `run.log`：面向人的日志
- `events.jsonl`：结构化 live event 流
- `manifest.json`：run 元数据与产物契约
- `summary.json`：最终 summary
- `aggregate.json`：对比与聚合结果
- `profiling.json`：runtime 与 task monitor 信息
- `trials.jsonl`：trial 级结果
- `metrics_wide.csv`：分析友好的宽表导出

Web UI 的大部分能力都是围绕这些产物和 live events 建立的。

## Web UI

内置 monitor 是一个打包到 `snowl` 里的 Next.js 应用。

当前结构：

- `/`：run gallery
- `/runs/[runId]`：run workspace
- `/compare`：历史 experiment 对比

主工作流：

- 先在 gallery 里选 run
- 进入 workspace 看模型与任务状态
- 下钻 runtime logs 和 pretask 诊断
- 如有需要，再去 compare 看历史对比

它是 run-first，而不是 experiment-first。

## 当前架构方向

Snowl 现在真正的下一阶段，不再是“再接几个 benchmark”。
真正最难、也最有价值的问题是 runtime 和 orchestration 工业化。

接下来最硬的方向包括：

- 并发调度
- build / sandbox / model-call 的 backpressure
- container 生命周期鲁棒性
- 失败后的 resume / recovery
- 更强的产物契约
- 长时间 run 的可观测性

如果你要做这部分，请先读 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 仓库地图

核心框架：

- `snowl/core/`
- `snowl/eval.py`
- `snowl/runtime/`
- `snowl/envs/`
- `snowl/model/`
- `snowl/agents/`

监控与 UI：

- `snowl/cli.py`
- `snowl/web/`
- `webui/`
- `snowl/_webui/`

benchmark 与 examples：

- `snowl/benchmarks/`
- `examples/`
- `references/`

验证与打包：

- `tests/`
- `pyproject.toml`
- `setup.py`

## 推荐阅读顺序

1. [AGENTS.md](./AGENTS.md)
2. [START_HERE.md](./START_HERE.md)
3. [ARCHITECTURE.md](./ARCHITECTURE.md)
4. [PLANS.md](./PLANS.md)
5. 再看你要改的子系统代码

## 状态说明

Snowl 已经有比较强的平台基础，但它还不是工业级 scheduler。

目前已经比较强的部分：

- 统一评测契约
- 官方 benchmark 覆盖
- 多模型 authoring
- container-aware trial execution
- 产物与监控

当前最难、也最值得投入的未完成部分：

- 工业级 runtime scheduling
- 更强的 fairness 与 backpressure
- container-heavy run 的 fault isolation 和 recovery
- 在不破坏契约的前提下走向多机/更大规模

这正是这个仓库接下来的重点。
