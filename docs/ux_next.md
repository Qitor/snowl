# Snowl UX Next Todo

目标：把 Live CLI 从“可看”升级到“可读、可诊断、可研究复用”。

---

## P0 - 信息主次与研究可复用

ID: UXN-001  
Title: 顶部 KPI Strip（指标主角化）  
Priority: P0  
Status: TODO  
Problem:
- 当前 `success_rate` 过于突出，scorer 指标不够醒目。
Definition of done:
- 增加固定 `KPI STRIP` 区域，仅展示评测指标（不混运行日志）。
- 支持 `primary_metric`（大号显示）+ `secondary_metrics`（紧凑显示）。
- 指标内容来自 `outcome.scores` 动态聚合，不写死 metric 名称。
- 至少展示：`avg`、`count`、`last`，并支持 `top-k`。

ID: UXN-002  
Title: 过程区/结果区强分区  
Priority: P0  
Status: TODO  
Problem:
- 运行态与结果态信息混杂，阅读负担高。
Definition of done:
- 左侧统一为过程态：`queue/stage/inflight/events`。
- 右侧统一为结果态：`output/judge json/metric explain/final score`。
- 默认布局与 `qa_dense`、`ops_dense` 都遵循该原则。

ID: UXN-003  
Title: 通用 Metric Spotlight Widget（panel_type）  
Priority: P0  
Status: DONE  
Problem:
- 缺少“指标总览组件”，不同 benchmark 不易复用。
Definition of done:
- 新增 `panel_type=metric_spotlight`。
- 支持显示：`avg / p50 / p90 / count / last / trend(delta window)`。
- 支持 `panels.yml` 配置 `primary_metric`、`top_k`、`window_size`。
- strongreject/terminalbench/osworld 都能直接挂载。

ID: UXN-004  
Title: 结果导出为研究友好格式（jsonl/csv）  
Priority: P0  
Status: TODO  
Problem:
- 当前主要是 JSON 文件，不利于大规模流式分析。
Definition of done:
- 每次 run 输出：
  - `trials.jsonl`（每个 trial 一行：task_result + scores + payload）
  - `events.jsonl`（运行事件流，一行一事件）
  - `metrics_wide.csv`（trial x metric 展平）
- 全部带 `schema_version` 与 `run_id` 字段。
- 文档说明字段契约与向后兼容策略。

---

## P1 - Live 感与可读性

ID: UXN-005  
Title: Live 更新稳定性（低闪烁 + 高频小更新）  
Priority: P1  
Status: DONE  
Problem:
- 当前仍有视觉闪动与刷新不均匀感。
Definition of done:
- Rich Live 使用固定刷新策略（e.g. 6-12 fps）+ 事件驱动强制刷新。
- 大面板内容采用“节流 + 增量截断”策略，避免整块跳动。
- 增加 `ui_refresh_profile`（smooth/balanced/low_cpu）配置。

ID: UXN-006  
Title: 语义色与状态图标规范化  
Priority: P1  
Status: DONE  
Problem:
- 颜色已有增强，但语义规范还不够统一。
Definition of done:
- 固定状态语义：`queued/querying/running/scoring/success/incorrect/error`。
- 每种状态有统一 icon + color token（跨主题不变语义）。
- 在 `task_queue/stage_widget/metric_spotlight` 三处一致展示。

ID: UXN-007  
Title: QA 模式结果区强化（Judge 可见性）  
Priority: P1  
Status: DONE  
Problem:
- QA 评测中 judge 判据可见性仍不足。
Definition of done:
- `qa_result` 显示：`model output`、`judge_json`、`verdict badge`、`final score`。
- 支持长文本折叠/展开（默认摘要 + 快捷展开）。
- scorer explain 与 judge json 可互相跳转定位。

---

## P2 - 可操作与可对比

ID: UXN-008  
Title: 命令栏增强（历史/补全/提示）  
Priority: P2  
Status: DONE  
Definition of done:
- 支持历史命令（↑↓）与基础补全（`/mode`, `/task`, `/status`）。
- 输入错误时给出 nearest suggestion。

ID: UXN-009  
Title: 指标对比视图（variant/model）  
Priority: P2  
Status: DONE  
Definition of done:
- `compare_board` 支持按 metric 排序、按 variant 分组、显示 rank 变化。
- 支持 `--ui-mode compare_dense` 或同等面板配置。

---

## 里程碑建议

Step A (MVP 可演示):
- UXN-001, UXN-002, UXN-004

Step B (体验升级):
- UXN-003, UXN-005, UXN-006, UXN-007

Step C (效率工具):
- UXN-008, UXN-009
