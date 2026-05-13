# Snowl 教程

AI Agent 安全评估框架 Snowl 的实战指南。

---

## 目录

1. [快速开始](#1-快速开始)
2. [项目结构](#2-项目结构)
3. [运行评估](#3-运行评估)
4. [编写自定义 Agent](#4-编写自定义-agent)
5. [编写自定义 Task](#5-编写自定义-task)
6. [编写自定义 Scorer](#6-编写自定义-scorer)
7. [Tool Middleware（工具中间件）](#7-tool-middleware工具中间件)
8. [Stateful Tool Execution（有状态工具执行）](#8-stateful-tool-execution有状态工具执行)
9. [内置 Benchmark](#9-内置-benchmark)
10. [创建新的 Benchmark 适配器](#10-创建新的-benchmark-适配器)
11. [多模型批量评估](#11-多模型批量评估)
12. [运行产物](#12-运行产物)
13. [常见问题](#13-常见问题)

---

## 1. 快速开始

### 安装

```bash
pip install -e .
```

### 运行内置 Benchmark

```bash
# 列出所有可用的 benchmark
snowl bench list

# 运行 StrongReject 安全评估
snowl eval examples/strongreject-official/project.yml

# 运行 ToolEmu 仿真评估
snowl eval examples/toolemu-emulation/project.yml

# 限制样本数量（快速测试）
snowl eval examples/strongreject-official/project.yml --limit 5
```

运行后，终端会展示带颜色、面板边框的 Rich TUI，实时显示模型调用、Agent 步骤和评分结果。

---

## 2. 项目结构

每个 Snowl 评估项目是一个包含四个文件的目录：

```
my-project/
  project.yml    # 配置：Provider、模型、Benchmark、运行参数
  agent.py       # Agent 定义：如何构建 Agent
  task.py        # Task 定义：加载哪个 Benchmark
  scorer.py      # Scorer 定义：如何评分
```

### project.yml 详解

```yaml
project:
  name: my-eval

provider:
  id: my-provider
  kind: openai_compatible
  base_url: https://api.example.com/v1
  api_key: sk-xxx
  timeout: 120

agent_matrix:
  models:
    - id: my_model
      model: my-model-v1
      metadata:
        company: acme
        source_type: open_source

eval:
  benchmark: strongreject
  split: test
  code:
    base_dir: .
    task_module: ./task.py
    agent_module: ./agent.py
    scorer_module: ./scorer.py
  limit: 10

runtime:
  max_running_trials: 2
  provider_budgets:
    my-provider: 100
```

关键字段说明：
- **provider**：LLM API 端点配置（兼容 OpenAI 接口）
- **agent_matrix.models**：要评估的模型变体列表
- **eval**：使用哪个 Benchmark、代码位置、样本限制
- **runtime**：并发限制和 Provider 预算

---

## 3. 运行评估

### 基本用法

```bash
snowl eval path/to/project.yml
```

### 常用参数

```bash
# 限制样本数
snowl eval project.yml --limit 5

# 无 TUI 输出（适用于脚本/CI）
snowl eval project.yml --no-ui

# 全屏仪表盘模式
snowl eval project.yml --cli-ui

# 自定义并发数
snowl eval project.yml --max-running-trials 4

# 恢复之前的运行
snowl eval project.yml --resume <run_id>

# 仅重试失败的 trial
snowl eval project.yml --rerun-failed-only

# 设置 Provider 预算
snowl eval project.yml --provider-budget my-provider=50
```

### Benchmark 命令

```bash
# 列出所有内置 benchmark
snowl bench list

# 直接运行内置 benchmark
snowl bench run strongreject --project project.yml

# 脚手架：创建新的 benchmark 适配器
snowl bench scaffold my-benchmark --out ./my-benchmark

# 验证 benchmark 适配器
snowl bench check my-benchmark --adapter ./adapter.py:MyAdapter
```

### 重试未完成的运行

```bash
snowl retry <run_id>
```

---

## 4. 编写自定义 Agent

Agent 只需满足两个条件：
- `agent_id: str` — 唯一标识符
- `async def run(self, state, context, tools=None) -> AgentState` — 执行循环

### 最简 Agent

```python
# agent.py
from snowl.core import agent as declare_agent, AgentState, AgentContext

class MyAgent:
    agent_id = "my_agent"

    async def run(self, state: AgentState, context: AgentContext, tools=None) -> AgentState:
        state.output = {"message": "Hello from my agent!"}
        state.stop_reason = "completed"
        return state

@declare_agent(agent_id="my_agent")
def agents():
    return [MyAgent()]
```

### 带 Tool 的 ReAct Agent

内置 `ReActAgent` 运行 Plan-Act-Observe 循环，支持 LLM 工具调用：

```python
# agent.py
from pathlib import Path
from snowl.agents import ReActAgent, build_model_variants
from snowl.core import agent as declare_agent
from snowl.model import OpenAICompatibleChatClient, ProjectModelEntry, ProjectProviderConfig

PROJECT_DIR = Path(__file__).resolve().parent

def _build_react_agent(model_entry: ProjectModelEntry, provider: ProjectProviderConfig):
    client = OpenAICompatibleChatClient(model_entry.config)
    return ReActAgent(
        model_client=client,
        agent_id="react_agent",
        max_steps=10,
    )

@declare_agent(agent_id="react_agent")
def agents():
    return build_model_variants(
        base_dir=PROJECT_DIR,
        agent_id="react_agent",
        factory=_build_react_agent,
    )
```

### 带 ToolMiddleware 的 Agent

注入中间件来拦截工具调用：

```python
from snowl.tools.middleware import LoggingMiddleware
from snowl.agents import ReActAgent

agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware()],
    max_steps=8,
)
```

### AgentState 字段

| 字段 | 类型 | 用途 |
|------|------|------|
| `messages` | `list[dict]` | 对话历史 |
| `actions` | `list[Action]` | 执行的工具调用 |
| `observations` | `list[Observation]` | 工具返回结果 |
| `output` | `dict \| None` | 最终输出 |
| `stop_reason` | `StopReason \| None` | Agent 停止原因 |

---

## 5. 编写自定义 Task

Task 定义加载哪些 Benchmark 样本：

```python
# task.py
from pathlib import Path
from snowl.core import task as declare_task, Task
from snowl.benchmarks.example_task import load_single_task
from snowl.benchmarks.strongreject import StrongRejectBenchmarkAdapter
from snowl.project_config import load_project_config

PROJECT = load_project_config(Path(__file__).parent)

@declare_task()
def task() -> Task:
    adapter = StrongRejectBenchmarkAdapter()
    return load_single_task(
        adapter,
        split=PROJECT.eval.split or "test",
        limit=PROJECT.eval.limit,
    )
```

`load_single_task` 是便捷封装。更灵活的用法：

```python
@declare_task()
def task() -> Task:
    adapter = MyBenchmarkAdapter(dataset_path="data.json")
    tasks = adapter.load_tasks(split="official", limit=10, filters={"suite": "banking"})
    return tasks[0]
```

---

## 6. 编写自定义 Scorer

Scorer 对 Agent 输出进行评估，产出数值分数：

### 同步 Scorer

```python
# scorer.py
from snowl.core import Scorer, Score, ScoreContext, TaskResult

class MyScorer:
    scorer_id = "my_scorer"

    def score(self, task_result: TaskResult, trace: dict, context: ScoreContext) -> dict[str, Score]:
        output = task_result.final_output or ""
        is_safe = "dangerous" not in output.lower()
        return {
            "safety": Score(value=1.0 if is_safe else 0.0, explanation="输出安全检查"),
        }

scorer = MyScorer()
```

### 异步 Scorer（适用于 LLM 评判）

```python
from snowl.core import AsyncScorer, Score, ScoreContext, TaskResult

class MyLLMJudge:
    scorer_id = "llm_judge"

    async def ascore(self, task_result: TaskResult, trace: dict, context: ScoreContext) -> dict[str, Score]:
        client = OpenAICompatibleChatClient(config)
        response = await client.generate([{"role": "user", "content": f"评估: {task_result.final_output}"}])
        return {
            "quality": Score(value=0.8, explanation=response.message.get("content", "")),
        }
```

### 组合式 Scorer

Snowl 提供内置的可组合评分器：

```python
from snowl.scorer import checkpoint_score, state_transition, tool_trace_policy

# 状态转换检查：验证状态是否按预期变化
utility = state_transition(metric_name="utility")

# 工具调用策略检查：验证 Agent 是否调用了禁止的工具
security = tool_trace_policy(metric_name="security")

# 加权组合评分
composite = checkpoint_score(
    metric_name="overall",
    weights={"utility": 0.5, "security": 0.5},
)
```

---

## 7. Tool Middleware（工具中间件）

工具中间件拦截工具调用和返回结果，支持日志、仿真、有状态执行等模式。

### ToolMiddleware 协议

```python
class ToolMiddleware(Protocol):
    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        """预处理工具调用参数，返回修改后的参数"""
        ...

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        """后处理工具返回结果，返回修改后的结果"""
        ...
```

### MiddlewareChain 组合

中间件通过 `MiddlewareChain` 组合：
- **调用** 正向流经：M1.intercept_call → M2.intercept_call → 工具执行
- **结果** 反向流经：工具 → M2.intercept_result → M1.intercept_result

### 内置中间件

| 中间件 | 用途 |
|--------|------|
| `LoggingMiddleware` | 记录所有调用和结果到 `.log` |
| `IdentityMiddleware` | 无操作直通（用于测试） |
| `EmulatedToolWrapper` | 用 LM 仿真替代真实工具返回 |
| `StatefulToolExecutor` | 用真实 Python 实现替代哨兵桩函数 |

### 自定义中间件示例

```python
from snowl.tools.middleware import ToolMiddleware

class TruncateMiddleware:
    """截断过长的工具返回结果"""

    async def intercept_call(self, tool_name: str, args: dict) -> dict:
        return args  # 直通

    async def intercept_result(self, tool_name: str, args: dict, result: Any) -> Any:
        if isinstance(result, str) and len(result) > 500:
            return result[:500] + "... (已截断)"
        return result
```

接入 Agent：

```python
agent = ReActAgent(
    model_client=client,
    middlewares=[LoggingMiddleware(), TruncateMiddleware()],
)
```

---

## 8. Stateful Tool Execution（有状态工具执行）

对于 AgentDojo 等工具需要跨调用修改共享状态的 Benchmark，Snowl 提供 `StatefulToolExecutor`：

### 工作原理

1. 桩工具返回 `{"__stateful__": True}`（哨兵值）
2. `StatefulToolExecutor.intercept_result()` 检测到哨兵
3. 委托给真实的 Python 实现来修改状态字典
4. 返回实际结果替代哨兵

### 银行业务示例

```python
from snowl.tools.stateful_executor import StatefulToolExecutor, make_stateful_stub_tool

# 创建带有初始状态的执行器
executor = StatefulToolExecutor(
    suite="banking",
    initial_state={
        "bank_account": {"balance": 1000.0, "iban": "DE89...", "transactions": []},
        "user_account": {"first_name": "Emma", "password": "pass123"},
    },
)

# 从 OpenAI Schema 创建桩工具
stub = make_stateful_stub_tool("get_balance", "查询余额", {"type": "object", "properties": {}})

# 接入 ReActAgent
agent = ReActAgent(model_client=client, middlewares=[executor], max_steps=10)

# Agent 运行后，检查状态变化
post_state = executor.get_post_state()
state_diff = executor.get_state_diff()  # [{path, op, value}, ...]
```

### 可用套件

| 套件 | 工具数 | 描述 |
|------|--------|------|
| `banking` | 11 | 余额查询、转账、定时交易、文件读写、用户管理 |
| `travel` | 18 | 酒店查询/预订、餐厅、租车、航班、行程管理 |

---

## 9. 内置 Benchmark

Snowl 内置 20+ Benchmark 适配器：

| Benchmark | 领域 | 类型 | 主指标 | 方向 |
|-----------|------|------|--------|------|
| `strongreject` | Agent 安全 | 安全 | strongreject | 越低越好 |
| `toolemu` | Agent 安全 | 安全 | risk_rate | 越低越好 |
| `agentdojo` | Agent 安全 | 安全 | agentdojo_score | 越高越好 |
| `agentharm` | Agent 安全 | 安全 | agentharm_safety | 越高越好 |
| `mask` | Agent 安全 | 安全 | mask_score | 越低越好 |
| `xstest` | Agent 安全 | 安全 | xstest_safety | 越高越好 |
| `bfcl` | Agent 能力 | 能力 | function_call_accuracy | 越高越好 |
| `terminalbench` | 网络安全 | 能力 | pass_rate | 越高越好 |
| `osworld` | 网络安全 | 能力 | success_rate | 越高越好 |
| `wmdp-cyber` | 网络安全 | 能力 | accuracy | 越高越好 |
| `wmdp-chem` | 化学风险 | 能力 | accuracy | 越高越好 |
| `sec_qa_v1/v2` | 网络安全 | 能力 | accuracy | 越高越好 |

运行任意 benchmark：

```bash
snowl bench run <benchmark-name> --project project.yml
```

---

## 10. 创建新的 Benchmark 适配器

### 脚手架

```bash
snowl bench scaffold my-benchmark --out ./my-benchmark
```

### 实现适配器

```python
# my-benchmark/adapter.py
from snowl.benchmarks.base_adapter import BaseBenchmarkAdapter
from snowl.benchmarks.base import BenchmarkInfo

class MyBenchmarkAdapter(BaseBenchmarkAdapter[dict]):
    name: str = "my_benchmark"
    description: str = "我的自定义 Benchmark"

    def benchmark_info(self) -> BenchmarkInfo:
        return BenchmarkInfo(
            name=self.name,
            display_name="My Benchmark",
            domain="agentic_safety",
            benchmark_type="safety",
            primary_metric="safety_score",
            higher_is_better=True,
        )

    def _row_to_sample(self, row, *, row_index, row_split, selected_count):
        return {
            "id": f"my-bench-{row_index}",
            "input": row["prompt"],
            "metadata": {"split": row_split, **row.get("metadata", {})},
        }

    def _env_spec(self) -> EnvSpec:
        return EnvSpec(env_type="local")
```

### 验证

```bash
snowl bench check my-benchmark --adapter ./my-benchmark/adapter.py:MyBenchmarkAdapter
```

---

## 11. 多模型批量评估

在 `agent_matrix.models` 中添加多个模型，即可并行评估对比：

```yaml
agent_matrix:
  models:
    - id: glm51
      model: glm-5.1-w4a8
      metadata:
        company: zhipu
        source_type: open_source
    - id: qwen3
      model: Qwen/Qwen3-32B
      metadata:
        company: alibaba
        source_type: open_source
    - id: gpt4o
      model: gpt-4o-2024-05-13
      provider:           # 单模型 Provider 覆盖
        base_url: https://api.openai.com/v1
        api_key: sk-xxx
```

Snowl 为每个 (task × model × sample) 组合创建一个 trial，结果在 Compare 面板中按指标排名展示。

---

## 12. 运行产物

每次 eval 运行在 `.snowl/runs/` 下生成一个目录：

```
.snowl/runs/20260513T040647Z/
  manifest.json          # 运行元数据（项目、模型、时间戳）
  plan.json              # Trial 计划（task × agent × sample 矩阵）
  events.jsonl           # 所有运行时事件的流式日志
  attempts.jsonl         # 每个 trial 的尝试记录
  outcomes.json          # 所有 trial 的最终结果
  aggregate.json         # 按 task/agent 聚合的指标
  leaderboard_rows.jsonl # 排名数据
  metrics_wide.csv       # 所有指标的平面 CSV
  run.log                # 人类可读日志
  report.html            # HTML 报告
```

### 关键文件

- **outcomes.json**：trial 键到 `{status, final_output, scores, usage, timing}` 的映射
- **aggregate.json**：按 (task, agent) 的指标均值和计数
- **events.jsonl**：行分隔 JSON 格式的运行时事件（模型 I/O、工具调用、评分）

---

## 13. 常见问题

### "模型名显示为 ?"

这通常是因为事件元数据嵌套在 `payload` 下。Snowl 的 `_pick()` 辅助方法会依次检查 `event[key]` → `event["payload"][key]` → `event["payload"]["payload"][key]`。如果 TUI 中看到 `?`，请确保你的事件在上述层级中包含了预期的键。

### "所有 trial 都报错"

检查 `run.log` 中的错误。常见原因：
- API Key 或 base_url 无效
- 模型名在 Provider 中不存在
- 超时设置过低（增大 `provider.timeout`）

### "没有加载到任何样本"

确保 Task 适配器的 `dataset_path` 指向存在的文件，且文件包含 JSON 数组，每项有 `prompt` 或 `input` 字段。

### Rich 面板显示异常

Snowl 使用 Rich 进行终端渲染。如果面板显示不正常：
- 确保终端支持 ANSI 转义码
- 使用 `--no-ui` 切换到纯文本输出
- 设置 `TERM=xterm-256color` 以获得更好的颜色支持

### AgentDojo 数据集如何生成

```bash
# 从 AgentDojo 参考代码生成数据集
PYTHONPATH=references/AgentDojo/src python -m snowl.benchmarks.agentdojo.build_dataset
```

生成的文件保存在 `references/AgentDojo/assets/`：
- `all_cases.json` — 320 个测试用例（36 无注入 + 284 有注入）
- `banking_tools.json` — 11 个银行工具 Schema
- `travel_tools.json` — 28 个旅行工具 Schema
