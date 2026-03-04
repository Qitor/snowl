## 1) 最佳用户体验流程

### A. 单按钮：Import → Generate Draft

入口放在编辑器顶部：

* **Import (URL/PDF)** → 选择 URL 或上传 PDF
* 点击后出现一个 side panel：**“Draft Generation”**

### B. 三阶段（非常重要，避免一次性胡编）

1. **Extract**（抽取）
2. **Normalize**（结构化）
3. **Draft**（生成 Markdown）

每一步都可显示“可验证的中间产物”，让用户信任系统。

---

## 2) 交互细节（你应该怎么做，才会很顺）

### Step 0：选择输入

* URL（优先）
* PDF 上传（次选）
* 复制粘贴摘要/段落（fallback）

### Step 1：系统生成“候选字段”并高亮置信度

右侧面板显示：

* Title (high confidence)
* Publication date (medium)
* Evaluator org (high)
* Risk domains detected (medium)
* Benchmarks detected (low/medium)
* Metrics + values (variable)

每一项都：

* 可一键接受/修改
* 显示引用位置（页码/段落）

> 你要让用户感觉：这是“带证据的抽取”，不是“编写”。

### Step 2：点击 “Insert Draft”

把生成的 Markdown 草稿插入 editor。

### Step 3：用户校对 → Validate → Publish

---

## 3) 关键：你必须采用“证据驱动”的生成格式

不要让模型直接“写 Markdown 成品”而不给证据。

你要让 LLM 输出同时包含：

* Markdown 草稿
* 每个字段的 evidence pointer（页码/段落）
* 不确定字段标记为 TODO

这样才能稳定、可信、可审计。

---

## 4) 建议的 LLM 输出协议（强烈推荐）

让 LLM 输出一个 JSON（或 function-call）：

```json
{
  "study": { ... },
  "evaluations": [ ... ],
  "results": [ ... ],
  "evidence_map": { "field_path": { "source": "...", "location": "...", "quote": "..." } },
  "warnings": [ ... ],
  "markdown_draft": "..."
}
```

你展示给用户看的可以是：

* markdown_draft
* warnings
* evidence_map（可折叠）

---

## 5) Prompt 设计（两段式最稳）

### Prompt 1：Extractor（只抽取，不写文章）

输入：PDF文本/HTML + 元信息
输出：结构化 JSON（严格 schema）

要求：

* 不知道就写 `null` 或 `TODO`
* 每个关键字段都要给 evidence（页码/段落）
* 禁止猜测

### Prompt 2：Renderer（把 JSON 变成标准 Markdown）

输入：JSON
输出：严格符合模板的 Markdown
不加入新信息

这样你会极大降低“幻觉”与“自由发挥”。

---

## 6) 你们需要的“标准 Markdown 模板”要支持 TODO 与证据

我建议模板里显式允许：

* `TODO:` 前缀
* Evidence 区块
* 自动插入 `location: "PDF p.X"`

示例（片段）：

```markdown
- risk_domain: TODO
- benchmark_variant: TODO
...
#### Evidence
- type: quote
  location: "PDF p.12"
  text: "..."
```

当 LLM 不确定时：

* 留 TODO
* 写明它为什么不确定（放 warnings）

---

## 7) 自动识别多模型 / 多实验的策略

现实论文通常是：

* 多风险域
* 多 benchmark
* 多模型
* 多 setting

所以抽取要做 “chunk by section”：

1. 找 evaluation sections（Methods / Evaluation / Experiments）
2. 找 tables / figures（metrics 常在表里）
3. 找 appendix（更多细节）
4. 按 risk domain 分组

LLM 不一定能一次吃下全文，所以用 **分段抽取 + 汇总合并** 更稳。

---

## 8) 质量控制（必须做，否则会崩）

### 必做的校验

* markdown → parse → JSON → validate
* required fields missing → block publish
* 数值校验（例如 percentage 要统一 0–1 或 0–100）

### 必做的“来源约束”

* 所有数值必须有 evidence pointer
* 没 evidence 的数值默认标 TODO

### UI 上必须暴露

* “哪些字段是模型猜的？”（理想：不允许猜）
* “哪些字段来自明确引用？”（高信任）

---

## 9) 最简单的 MVP（1-2 周可落地）

你们可以先只做：

* URL/PDF → Extract title/date/evaluator
* 自动识别 risk domain（粗粒度）
* 自动生成 1 个 evaluation block + 1 个 result block（哪怕是 TODO）

核心是把 pipeline 跑通。

之后再迭代：

* table extraction
* 多 evaluation
* evidence mapping
* benchmark variant 对齐

---

## 10) 你下一步可以直接让 Codex 做的任务列表

我给你一个清晰的工程 TODO：

1. **Markdown Template v1**（固定字段名）
2. **Parser**：markdown → JSON（Study/Eval/Result）
3. **Validator**：JSON schema + 错误定位到行号
4. **Import UI**：URL/PDF 上传 → text extraction
5. **LLM Extractor**：text → structured JSON + evidence
6. **Renderer**：structured JSON → markdown_draft
7. **Insert Draft**：写入 editor
8. **Warnings Panel**：显示 TODO + 缺失字段 + evidence 缺失
9. **Publish Gate**：无 error 才允许发布


