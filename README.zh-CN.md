# Snowl（中文说明）

[English](./README.md) | [简体中文](./README.zh-CN.md)

Snowl 是一个 Agent 评测框架，并且正在朝工业级评测平台收敛。

它的持久核心契约是：

- 定义 `Task`
- 定义 `Agent`
- 定义 `Scorer`
- 展开成 `Task x AgentVariant x Sample`
- 用 `snowl eval path/to/project.yml` 运行

其余复杂度都由平台层承担：

- benchmark 适配
- 多模型展开
- provider-aware 并发调度
- container/runtime 编排
- 产物落盘
- CLI + Web operator 工作流

## 文档入口

- [START_HERE.md](./START_HERE.md)：最快速的仓库导览
- [ARCHITECTURE.md](./ARCHITECTURE.md)：当前架构与 runtime 方向
- [PLANS.md](./PLANS.md)：路线图与执行优先级
- [AGENTS.md](./AGENTS.md)：给 coding agent 的仓库规则
- [docs/runtime_scheduling.md](./docs/runtime_scheduling.md)：runtime 调度设计文档
- [docs/codex_best_practices.md](./docs/codex_best_practices.md)：Codex 使用建议

## 当前产品形态

Snowl 现在已经支持：

- 以 `project.yml` 为正式入口
- 通过 `agent_matrix.models` 做项目级多模型评测
- 内置 benchmark：
  - `strongreject`
  - `terminalbench`
  - `osworld`
  - `toolemu`
  - `agentsafetybench`
- provider-aware 的本地并发治理
- 面向 terminal / GUI benchmark 的 container-aware runtime
- `.snowl/runs/` 下的完整评测产物
- 面向 operator 的 Next.js Web monitor
- 前台 plain CLI + 后台 Web sidecar 的默认运行模式
- resume 与 rerun-failed

当前部署目标仍然是：本地单机评测。

## 安装

```bash
cd /Users/morinop/coding/snowl_v2
pip install -e .
```

安装阶段会一并构建内置 Web UI。

## 准备 reference 仓库

若使用官方 example，需要把外部 benchmark 仓库放在这些固定目录：

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

## 快速开始

### 跑官方 example

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/strongreject-official/project.yml
```

其他 example：

```bash
snowl eval /Users/morinop/coding/snowl_v2/examples/terminalbench-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/osworld-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/toolemu-official/project.yml
snowl eval /Users/morinop/coding/snowl_v2/examples/agentsafetybench-official/project.yml
```

### 通过 benchmark adapter 运行

```bash
snowl bench list
```

```bash
snowl bench run terminalbench \
  --project /Users/morinop/coding/snowl_v2/examples/terminalbench-official/project.yml \
  --split test
```

## 默认运行体验

默认 CLI 行为是：

- 前台：评测本身的 plain terminal progress / logging
- 后台：自动拉起 Web monitor sidecar
- 可选：`--cli-ui` 打开旧 live CLI 面板

典型命令：

```bash
snowl eval /absolute/path/to/my-project/project.yml
```

实际行为：

1. 终端先打印 project/run 启动信息
2. 评测以前台任务形式开始执行
3. run 初始化完成后，再打印 Web URL，例如 `http://127.0.0.1:8765`
4. 停掉 eval 时，也会一起停掉这次自动拉起的 monitor sidecar

常用参数：

- 过滤：`--task`、`--agent`、`--variant`
- runtime 预算：
  - `--max-running-trials`
  - `--max-container-slots`
  - `--max-builds`
  - `--max-scoring-tasks`
  - `--provider-budget provider_id=n`
- 可靠性：`--resume`、`--rerun-failed-only`
- monitor：`--no-web-monitor`
- 旧 live CLI：`--cli-ui`

手动 monitor 模式仍然可用：

```bash
snowl web monitor --project /absolute/path/to/my-project --host 127.0.0.1 --port 8765
```

## `project.yml` 是唯一正式入口

Snowl 现在把单个 YAML 文件作为一条评测 run 的正式入口。

推荐结构：

```text
my-project/
  project.yml
  task.py
  agent.py
  scorer.py
  tool.py        # 可选
```

示例：

```yaml
project:
  name: strongreject-qwen-sweep
  root_dir: .

provider:
  id: siliconflow
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

eval:
  benchmark: strongreject
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
    tool_module: ./tool.py
  split: test
  limit: 50

runtime:
  max_running_trials: 8
  max_container_slots: 0
  max_builds: 2
  max_scoring_tasks: 8
  provider_budgets:
    siliconflow: 8
```

语义：

- `project.root_dir`：项目根目录，用于产物路径和相对路径解析
- `eval.code.base_dir`：代码加载根目录
- `provider`：本次评测使用的远程模型 provider
- `agent_matrix.models`：被测模型列表，会展开成多个 `AgentVariant`
- `judge.model`：可选 judge/scorer 模型，和被测模型分离
- `runtime.provider_budgets`：provider 级并发预算

目录结构没有被取消，而是改成由 YAML 显式声明。

## 多模型 Authoring

`agent.py` 推荐模式：

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

这套模式现在已经同时覆盖 QA 型 example 和 TerminalBench、OSWorld 这种 container-heavy example。

## Runtime 调度模型

Snowl 正在从粗粒度 semaphore 走向显式的 phase-aware scheduler。

当前 runtime 预算已经拆成：

- `max_running_trials`：agent 执行并发
- `max_container_slots`：container / sandbox 容量
- `max_builds`：build/pull/setup 并发
- `max_scoring_tasks`：scorer 并发
- `provider_budgets[provider_id]`：provider 级远程请求并发

当前运行时已经体现两个关键设计：

- provider 是 remote 模型并发的主限制边界
- scoring 不再默认占用 agent execution 的同一个 slot

因此 QA 任务和 container-heavy benchmark 可以共用一套 scheduler，只是资源消耗不同。

## 产物与可观测性

每次 run 的产物目录：

```text
<project>/.snowl/runs/<run_id>/
```

关键产物包括：

- `manifest.json`
- `plan.json`
- `summary.json`
- `aggregate.json`
- `profiling.json`
- `trials.jsonl`
- `events.jsonl`
- `run.log`

可观测性入口：

- CLI：面向 operator 的前台日志/进度
- Web：
  - `/`：run gallery / operator board
  - `/runs/[runId]`：单 run workspace
  - `/compare`：次级历史对比视图

running run 应该在启动后立刻变得可见。Snowl 会尽早写入 bootstrap artifacts，这样 Web 在 run 完成前就能显示 planned trials、visible tasks、models 和 progress。

## Examples

参见 [examples/README.md](./examples/README.md)。

## 开发检查

Python tests：

```bash
pytest -q
```

runtime 重点检查：

```bash
pytest -q tests/test_eval_autodiscovery.py tests/test_runtime_controls_and_profiling.py tests/test_resource_scheduler.py tests/test_cli_eval.py
```

合成调度基线：

```bash
python scripts/runtime_scheduler_benchmark.py
```

Web UI typecheck：

```bash
cd webui
npm run -s typecheck
```

安装 sanity：

```bash
pip install -e .
```
