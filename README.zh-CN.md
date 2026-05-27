# Snowl

[![CI](https://github.com/Qitor/snowl/actions/workflows/ci.yml/badge.svg)](https://github.com/Qitor/snowl/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![Benchmarks](https://img.shields.io/badge/benchmarks-25%2B-success)
[![Docs](https://img.shields.io/badge/docs-site-blue)](https://qitor.github.io/snowl)
[English](./README.md) | [简体中文](./README.zh-CN.md)

**Snowl** 是一个框架无关的 AI Agent 评测引擎。用 3 行代码即可对任意 Agent 运行任意 Benchmark，获取可复现的评分并进行公平对比。

```python
from snowl import quick_eval

result = quick_eval(
    agent=lambda prompt: "I cannot help with that.",
    benchmark="strongreject",
    limit=10,
)
print(f"Pass rate: {result.pass_rate:.0%}  Cost: {result.total_tokens} tokens")
```

## 安装

```bash
pip install snowl
```

框架支持：

```bash
pip install snowl[qitos]       # QitOS agents
pip install snowl[langgraph]   # LangGraph agents
pip install snowl[openai]      # OpenAI Agents SDK
```

Benchmark 扩展包（26 个 benchmark 适配器）：

```bash
pip install snowl-evals                   # 全部 benchmark
pip install snowl-evals[cyber]            # 网络安全类
pip install snowl-evals[safety]           # 安全类
pip install snowl-evals[coding]           # 编码类
```

## 30 秒快速体验

**Python API** — 评测任意可调用对象：

```python
from snowl import quick_eval

# 评测简单函数
result = quick_eval(
    agent=lambda prompt: "hello",
    samples=[{"id": "s1", "input": "Say hi", "target": "hello"}],
    scorer="includes",
)

# 评测内置 benchmark
result = quick_eval(agent=my_async_fn, benchmark="bfcl", limit=50)
```

**CLI** — 运行完整评测项目：

```bash
snowl bench list                                    # 列出 benchmark
snowl eval project.yml                              # 运行评测
snowl bench run strongreject --split test --limit 10  # 运行单个 benchmark
snowl retry run-20260427T120000Z                    # 重试失败项
```

## 为什么选择 Snowl

| 问题 | Snowl 的方案 |
|------|-------------|
| Agent 难以接入 benchmark | 3 行 `quick_eval()` + Adapter SDK（QitOS、LangGraph、OpenAI Agents） |
| 安全评测浮于表面 | 内置评分器：canary 泄露、工具调用策略、工作区 diff、命令检查、注入评分 |
| 不同模型的分数不可比 | 成本感知评分、分离验证器、工作耗时指标 |
| 运行难以复现 | 确定性 Task x AgentVariant x Sample 规划，完整产物链 |
| Terminal/GUI/Web 任务行为差异 | Phase-aware 运行时，Docker 沙箱、容器隔离、AIMD 流控 |

## 核心概念

```text
Task × Agent × Scorer → TrialOutcome → Aggregated Result
```

- **Task**: 评测什么（样本 + 环境规格）
- **Agent**: 被评测什么（任意 Python 可调用对象或 Agent Protocol）
- **Scorer**: 如何评判（15+ 内置评分器：includes、match、model-as-judge、canary、tool trace、...）
- **Runtime**: 在哪里运行（本地、Docker 沙箱、GUI 容器）

## 内置 Benchmark

25+ 个涵盖安全与能力的 benchmark：

| 类别 | Benchmark |
|------|----------|
| 安全 | StrongReject、XSTest、AgentHarm、CoConot、FORTRESS、MASK、SevenLLM |
| 网络安全 | WMDP、CyberMetric、SecQA、CyBench、CyberGym |
| 工具使用 / Agent | BFCL、AgentDojo、AgentBench-OS、ToolEmu、IPI Coding Agent |
| 能力 | GAIA、Tau-Bench、OSWorld、TerminalBench、SWE-Bench、HumanEval |
| 自定义 | JSONL、CSV 适配器，适用于自己的数据集 |

## 每次运行你将获得

每次运行都会生成独立的产物目录：

```text
.snowl/runs/<run_id>/
  outcomes.json          # 逐样本结果
  aggregate.json         # 汇总指标
  events.jsonl           # 完整事件流
  leaderboard_rows.jsonl # 排名结果
  recovery.json          # 重试状态
```

## 高级特性

- **工具调用策略中间件**：运行时强制执行 forbidden tools、max calls、参数约束等策略
- **成本感知评分**：CostNormalizedScorer 计算 score/dollar，排行榜支持 `--cost-aware`
- **注入评分矩阵**：多维度安全评分（instruction_followed、security_breached、graceful_rejection、partial_compliance）
- **框架适配器**：QitOS、LangGraph、OpenAI Agents SDK 三大框架的深度集成，含丰富 trace 事件
- **容器隔离**：TerminalBench 和 OSWorld 通过 ContainerProvider entry_point 实现容器沙箱

## 文档

- [Getting Started](https://qitor.github.io/snowl/getting-started/)
- [Tutorials](https://qitor.github.io/snowl/tutorials/)
- [API Reference](https://qitor.github.io/snowl/api-reference/)
- [Architecture](https://qitor.github.io/snowl/architecture/)

## 开发

```bash
pip install -e ".[dev]"
pytest -q
```

安装健康检查：

```bash
python -m snowl.check
```

## 贡献

Snowl 需要关心 AI Agent 安全性和可测量性的贡献者。推荐入门方向：

- 添加 benchmark 适配器
- 改进评分器
- 编写框架适配器（CrewAI、AutoGen、PydanticAI）
- 编写真实评测工作流的文档

## 许可证

详见仓库许可证文件。
