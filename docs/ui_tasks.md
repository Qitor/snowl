# Snowl Live UI 专项任务清单

目标：把 `snowl eval` 的 Live CLI 从“日志可见”升级为“评测可解释、可监控、可操作”的控制台。

总原则：
- 优先信息正确与可解释，再做视觉增强。
- 所有面板信息都来自统一事件契约，避免 benchmark 特判散落在 UI 层。
- 交互动作必须有 no-ui 等价命令，保证可复现。

---

## A. 信息架构（先统一数据，再做界面）

ID: UI-A-001  
Title: 定义 Live UI 统一事件契约（trace/env/scorer/control）  
Priority: P0  
Status: DONE  
Definition of done:
- 定义 `event.phase`（plan/env/task/agent/scorer/error/control/summary）。
- 每条事件至少包含：`run_id task_id agent_id variant_id ts message payload`。
- `TaskStatus` 统一：`queued/running/scoring/success/incorrect/error/cancelled/limit_exceeded`。

ID: UI-A-002  
Title: 定义 Task Monitor 状态模型（可切换任务监控）  
Priority: P0  
Status: DONE  
Depends on: UI-A-001  
Definition of done:
- 维护 `TaskViewModel`：当前状态、step、耗时、最近动作、最近观测、评分结果。
- 支持按 `task_id` 切换 monitor 焦点（active task -> selected task）。
- 状态迁移图在文档中明确（含异常分支）。

ID: UI-A-003  
Title: 定义 Scorer Explain Schema（可解释评分）  
Priority: P0  
Status: DONE  
Depends on: UI-A-001  
Definition of done:
- 每个 metric 支持结构化解释：`metric/value/evidence/reason/raw`。
- model-as-judge 支持展示“模板填充后 prompt + judge json”。
- UI 可直接渲染 explain，无需 benchmark-specific parsing。

---

## B. Eval Overview（总览面板）

ID: UI-B-001  
Title: 实现 Eval Overview 顶部总览面板  
Priority: P0  
Status: DONE  
Depends on: UI-A-001  
Definition of done:
- 展示：benchmark、run_id、总任务数、完成数、成功率、吞吐、错误率。
- 展示当前过滤器（task/agent/variant/status）与运行模式（live/compact）。
- 首屏加载时不再出现 `0/0` 误导状态。

ID: UI-B-002  
Title: 实现进度与资源概览（并发/容器/模型调用）  
Priority: P1  
Status: TODO  
Depends on: UI-B-001  
Definition of done:
- 进度条显示 trial/task 维度进展。
- 展示并发控制：`max_trials/max_sandboxes/max_model_calls/max_builds`。
- 展示当前活跃容器数与模型调用 in-flight 数。

---

## C. Task Monitor（可切换每个任务进展状态）

ID: UI-C-001  
Title: 实现 Task 列表面板（状态切换监控）  
Priority: P0  
Status: DONE  
Depends on: UI-A-002, UI-B-001  
Definition of done:
- 列出所有 task（或 sample-task 单元）并显示实时状态/耗时/重试数。
- 支持按状态筛选：`queued/running/scoring/failed/success`。
- 支持切换焦点到任一 task（键盘/命令栏都可）。

ID: UI-C-002  
Title: 实现 Active/Selected Task Detail 面板  
Priority: P0  
Status: DONE  
Depends on: UI-C-001  
Definition of done:
- 展示当前 task 的 instruction/input/metadata/env_spec。
- 展示当前 step、最近 action、最近 observation、最近工具调用。
- 支持“锁定查看 selected task，不被 active task 自动抢焦点”。

ID: UI-C-003  
Title: Task 执行时间线（Timeline）  
Priority: P1  
Status: TODO  
Depends on: UI-C-002  
Definition of done:
- 展示 `queued -> env_start -> run -> scoring -> done` 时间线。
- 每个阶段显示持续时间、关键事件摘要、失败点定位。
- 支持展开查看原始事件 payload。

---

## D. Panel Type System（通用面板体系）

ID: UI-D-001  
Title: 定义共性 `panel_type` 规范与渲染协议  
Priority: P0  
Status: TODO  
Depends on: UI-A-003, UI-C-002  
Definition of done:
- 定义标准 panel_type：`overview/task_queue/task_detail/env_timeline/action_stream/observation_stream/model_io/scorer_explain/compare_board/failures`。
- 每个 panel_type 约定输入数据模型与最小字段（schema）。
- UI 渲染层不包含 benchmark 名称分支判断。

ID: UI-D-002  
Title: 实现 panel_type 注册与布局编排器  
Priority: P0  
Status: TODO  
Depends on: UI-D-001  
Definition of done:
- 支持注册 panel renderer（registry）并按配置组装布局。
- 支持默认布局 + benchmark 覆盖布局（不改核心代码即可切换）。
- 支持 panel 的可见性条件（如仅在 env 事件出现后显示 env_timeline）。

ID: UI-D-003  
Title: 实现 benchmark -> panel_type 配置映射（非硬编码）  
Priority: P0  
Status: TODO  
Depends on: UI-D-002, UI-C-003  
Definition of done:
- StrongReject/TerminalBench/OSWorld 仅通过配置声明使用的 panel_type 与数据映射。
- 映射支持 `source`（event/trace/payload path）+ `transform`（字段转换）+ `visibility`。
- 新 benchmark 接入仅需新增映射配置文件，不改 UI core。

ID: UI-D-004  
Title: 为已实现三大 benchmark 落地 panel 配置与迁移  
Priority: P0  
Status: TODO  
Depends on: UI-D-003  
Definition of done:
- 为 `strongreject` 提供面板配置：至少包含 `overview/task_queue/task_detail/model_io/scorer_explain/failures`。
- 为 `terminalbench` 提供面板配置：至少包含 `overview/task_queue/task_detail/env_timeline/action_stream/observation_stream/scorer_explain/failures`。
- 为 `osworld` 提供面板配置：至少包含 `overview/task_queue/task_detail/env_timeline/action_stream/observation_stream/scorer_explain/failures`。
- 将当前 UI 中与三者相关的直连展示逻辑迁移为“读取配置 + 通用 panel_type 渲染”。
- 提供配置文件地址清单与加载优先级（默认配置 < benchmark 覆盖 < 用户覆盖）。
- 增加三 benchmark 的 UI 快照/验收测试，验证配置生效且无 benchmark 名称硬编码分支。

---

## E. 交互与命令栏（接近 Claude Code）

ID: UI-E-001  
Title: 实现命令栏（Command Palette）  
Priority: P0  
Status: DONE  
Depends on: UI-C-001  
Definition of done:
- 支持命令：`/task /agent /variant /status /focus /rerun /explain`。
- 输入反馈即时显示，错误命令给出可执行提示。
- 命令效果即时反映到 Overview + Task Monitor。

ID: UI-E-002  
Title: 键盘交互标准化  
Priority: P1  
Status: DONE  
Depends on: UI-E-001  
Definition of done:
- `Tab` 切面板，`j/k` 选 task，`Enter` 展开详情，`/` 打开命令栏。
- `p` pause/resume、`f` failed-focus、`r` rerun-failed 保持兼容。
- 键位帮助在 UI 可见并可折叠。

ID: UI-E-003  
Title: no-ui 等价命令与复现信息  
Priority: P0  
Status: DONE  
Depends on: UI-E-001  
Definition of done:
- 每个交互动作都可映射为 CLI flags。
- `profiling.json` 与 `run.log` 写入 `interaction.equivalent_cli`。
- parity 测试覆盖 interactive vs scripted 结果一致性。

---

## F. 视觉风格（Snow OWL）

ID: UI-F-001  
Title: Snow OWL 视觉主题变量化  
Priority: P1  
Status: DONE  
Depends on: UI-B-001  
Definition of done:
- 统一颜色 token（ice-blue/cyan/slate/alert）。
- 面板标题、进度、状态色统一规范。
- 高对比与低噪声模式可切换。

ID: UI-F-002  
Title: 炫酷 Banner 与品牌化页眉  
Priority: P1  
Status: DONE  
Depends on: UI-F-001  
Definition of done:
- Banner 支持宽终端/窄终端两种版本。
- 不抢占核心信息区域，支持一键收起。
- 录屏展示观感稳定。

---

## G. 性能与稳定性

ID: UI-G-001  
Title: 刷新节流与缓冲上限  
Priority: P0  
Status: DONE  
Depends on: UI-A-001  
Definition of done:
- 刷新频率可配置（默认 80ms），事件缓冲可配置上限。
- 高事件速率下无 runaway memory。
- 有 `ui.throttle` 可观测事件。

ID: UI-G-002  
Title: 长跑稳定性压测（3 benchmarks）  
Priority: P0  
Status: TODO  
Depends on: UI-G-001, UI-D-001, UI-D-002, UI-D-003, UI-D-004  
Definition of done:
- strongreject/terminalbench/osworld 长跑期间 UI 不崩溃、不花屏。
- 任务切换 monitor 无卡顿、无错位。
- 崩溃时保底降级到 text renderer。

---

## H. 测试与验收

ID: UI-H-001  
Title: Snapshot 测试（Overview + Task Monitor）  
Priority: P0  
Status: TODO  
Depends on: UI-B-001, UI-C-001, UI-C-002  
Definition of done:
- 固定关键界面快照：初始/运行中/失败/完成。
- 覆盖 narrow terminal 降级视图。
- 覆盖无 rich 环境 fallback 视图。

ID: UI-H-002  
Title: 端到端验收脚本（Demo-ready）  
Priority: P0  
Status: TODO  
Depends on: UI-D-001, UI-D-002, UI-D-003, UI-D-004, UI-E-001  
Definition of done:
- 一条命令可演示 pause/filter/task切换/score explain/rerun。
- 录屏脚本与文档完成。
- 产出 checklist：信息完整性、可解释性、可复现性。

---

## 建议执行顺序

Step 1:
- UI-A-001, UI-A-002, UI-A-003

Step 2:
- UI-B-001, UI-C-001, UI-C-002

Step 3:
- UI-D-001, UI-D-002, UI-D-003, UI-D-004

Step 4:
- UI-E-001, UI-E-002, UI-E-003

Step 5:
- UI-F-001, UI-F-002, UI-G-001

Step 6:
- UI-H-001, UI-G-002, UI-H-002
