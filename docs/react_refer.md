## 总体架构（你让 Codex照这个搭）

**核心循环（控制器）**：

1. 构造 messages（system + user + 历史）
2. 调用 LLM
3. 如果返回 **tool_calls**：

   * 逐个执行（或按你要求一次一个）本地 tool
   * 将结果以 `role="tool"` 回填到 messages
   * 继续下一轮
4. 如果返回最终文本：结束

OpenAI 的 tool calling 流程本质上就是：模型提出工具调用请求，你执行后把结果再喂回模型，直到模型产出最终回答。([OpenAI开发者][1])

---

## 1) System Prompt 模板（必须包含 `{tool_schema}` 占位符）

> 这份 prompt **同时**满足：
>
> * 你要求的 `{tool_schema}` 占位符
> * 明确告知 coding agent：实现时必须把 tool schema 注入到 system prompt 里
> * 兼容两条路线（原生 tools 或 JSON fallback）

```text
You are a Reasoning & Acting (ReAct) agent.

You solve the user's task by iterating:
Plan -> Act (call a tool) -> Observe -> Update plan ...
Repeat until you can provide a final answer.

========================
TOOL SCHEMA (INJECTED AT RUNTIME)
{tool_schema}
========================

IMPORTANT FOR THE CODING AGENT IMPLEMENTING THIS SYSTEM:
- The placeholder "{tool_schema}" MUST be replaced at runtime with the actual tool definitions (names, descriptions, and JSON argument schemas).
- The controller MUST pass this system prompt (with "{tool_schema}" filled) into the LLM request.
- You may ONLY call tools that appear in the injected tool schema.

## Preferred Tool Calling
If the API supports native tool calling, request tools via the API's "tools" parameter and use tool calls in your response when needed.

## Fallback (JSON Action Protocol)
If native tool calling is not available, you MUST output a single JSON object with either:
(A) tool_call  { "type":"tool_call", "tool":"...", "arguments":{...} }
(B) final      { "type":"final", "answer":"..." }
The controller will execute the tool and provide the Observation back.

## Behavioral Rules
- Use tools whenever needed to get real data or perform actions. Do NOT fabricate tool outputs.
- Call at most ONE tool per step (one action at a time). Wait for the tool result before proceeding.
- If you have enough information, provide the final answer immediately.
- Keep the final answer concise and directly helpful.
```

---

## 2) Tool Schema 设计（建议你让 Codex按 OpenAI tools JSON schema 做）

OpenAI Chat Completions 的工具定义通常长这样（每个 tool 是一个 function，带 name/description/parameters JSON schema）。([OpenAI开发者][1])

**示例工具定义（你可以扩展）：**

```python
TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "calc",
      "description": "Evaluate a basic arithmetic expression safely.",
      "parameters": {
        "type": "object",
        "properties": {
          "expression": {"type": "string", "description": "Arithmetic expression, e.g. '3*(2+5)'"}
        },
        "required": ["expression"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "search_kb",
      "description": "Search internal knowledge base for a query string.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        },
        "required": ["query"],
        "additionalProperties": False
      }
    }
  }
]
```

---

## 3) 工具实现与注册（Python）

你让 Codex 实现一个工具注册表，name -> callable：

```python
import json, re
from typing import Any, Callable, Dict

def calc(expression: str) -> str:
    # 极简安全校验（按需加白名单）
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expression):
        return "ERROR: unsafe expression"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"ERROR: {e}"

def search_kb(query: str) -> str:
    kb = {
        "react agent": "A React agent typically refers to a UI that interacts with an agent service via streaming chat + tool execution.",
        "react": "React is a JavaScript library for building user interfaces."
    }
    q = query.lower()
    for k, v in kb.items():
        if k in q:
            return v
    return "NOT_FOUND"

TOOL_IMPL: Dict[str, Callable[..., str]] = {
    "calc": calc,
    "search_kb": search_kb,
}
```

---

## 4) **关键点：tool schema 注入到 system prompt**（你特别强调的）

你让 Codex 必须实现类似：

```python
def render_tool_schema_for_prompt(tools: list[dict]) -> str:
    # 让 prompt 更可读：把 tools JSON pretty print
    return json.dumps(tools, ensure_ascii=False, indent=2)

SYSTEM_PROMPT_TEMPLATE = open("system_prompt.txt", "r", encoding="utf-8").read()

def build_system_prompt(tools: list[dict]) -> str:
    injected = render_tool_schema_for_prompt(tools)
    return SYSTEM_PROMPT_TEMPLATE.replace("{tool_schema}", injected)
```

> 这一步就是你要的：**实现 ReAct agent 需要把 tool schema 替换到 system prompt 里面**（注入后再调用 LLM）。

---

## 5) 路线 A（推荐）：**原生 tool calling** 控制器（Chat Completions）

OpenAI Chat Completions 支持通过请求参数传入 `tools`，模型会在需要时返回 `tool_calls`，你执行后以 `role="tool"` 回传。([OpenAI开发者][1])

让 Codex 实现这个“强约束循环”（**每轮最多一个 tool call**，更像 ReAct）：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1",
    api_key="YOUR_KEY",
)

def run_react(user_text: str, tools: list[dict], model: str, max_steps: int = 10) -> str:
    system_prompt = build_system_prompt(tools)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            # 强制每次最多一个工具调用（不同兼容端支持程度不同）
            tool_choice="auto",
            temperature=0.2,
        )

        msg = resp.choices[0].message

        # 1) 如果模型直接给最终内容
        if getattr(msg, "tool_calls", None) is None or len(msg.tool_calls) == 0:
            # 有的实现把文本放在 msg.content
            return msg.content or ""

        # 2) 有工具调用：这里按 ReAct 规则只执行一个
        tool_call = msg.tool_calls[0]
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments or "{}")

        impl = TOOL_IMPL.get(tool_name)
        if impl is None:
            tool_result = f"ERROR: unknown tool '{tool_name}'"
        else:
            try:
                tool_result = impl(**tool_args)
            except TypeError as e:
                tool_result = f"ERROR: bad arguments for tool '{tool_name}': {e}"
            except Exception as e:
                tool_result = f"ERROR: tool '{tool_name}' failed: {e}"

        # 把 assistant 的 tool_call 消息加入历史（很多兼容端要求保留）
        messages.append(msg)

        # 把工具结果以 role=tool 回传给模型
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

    return "ERROR: max_steps reached without final answer."
```

**注意（工程关键点）**

* 你必须把模型的 tool call message append 到历史，再 append tool result message；这是标准交互模式。([OpenAI开发者][1])
* “OpenAI-compatible”服务端对 `tool_choice`、`role="tool"`、`tool_call_id` 的支持程度可能不同；所以需要兜底路线 B。([docs.vllm.com.cn][2])

---

## 6) 路线 B（兜底）：**JSON Action Protocol**（不依赖 `tools` 参数）

适用场景：你的 OpenAI-compatible 端点**没有完整实现 tools/tool_calls**，但能稳定输出文本。

做法：

* system prompt 里要求模型输出严格 JSON：`{"type":"tool_call"...}` 或 `{"type":"final"...}`
* 你解析 JSON，执行工具，再把 Observation 作为新消息喂回去。

控制器示例（Codex照抄实现）：

```python
def run_react_json(user_text: str, tools: list[dict], model: str, max_steps: int = 10) -> str:
    system_prompt = build_system_prompt(tools)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""

        try:
            obj = json.loads(content)
        except json.JSONDecodeError:
            # 如果模型没按 JSON 输出，给它一次“纠偏”机会
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "system", "content": "FORMAT ERROR: Output must be a single valid JSON object. Try again."})
            continue

        if obj.get("type") == "final":
            return obj.get("answer", "")

        if obj.get("type") != "tool_call":
            messages.append({"role": "system", "content": "FORMAT ERROR: JSON.type must be 'tool_call' or 'final'."})
            continue

        tool_name = obj.get("tool")
        args = obj.get("arguments") or {}

        impl = TOOL_IMPL.get(tool_name)
        if impl is None:
            tool_result = f"ERROR: unknown tool '{tool_name}'"
        else:
            try:
                tool_result = impl(**args)
            except Exception as e:
                tool_result = f"ERROR: tool '{tool_name}' failed: {e}"

        # 把模型这步输出记录下来
        messages.append({"role": "assistant", "content": content})

        # Observation 回填
        messages.append({"role": "system", "content": f"OBSERVATION: {tool_result}"})

    return "ERROR: max_steps reached without final answer."
```

---

## 7) 你应该让 Codex实现的“必备工程护栏”

这些会显著提高稳定性（尤其是 ReAct 循环）：

1. **严格 schema**：`additionalProperties: false`，required 字段清晰（减少模型乱填）
2. **工具白名单**：只允许调用 schema 里出现的工具名
3. **一步一工具**：即便模型一次返回多个 tool_calls，也只执行第一个（或强制 tool_choice / 提示词约束）
4. **错误回传**：工具报错要原样作为 Observation 回填，让模型自我修正
5. **最大步数与超时**：避免死循环
6. **日志与可复现**：记录每轮 messages / tool args / tool result，方便调试

---

## 8) 你给 Codex 的任务清单（可以直接复制给它）

* [ ] 实现 `TOOLS`（OpenAI tools schema）
* [ ] 实现 `TOOL_IMPL`（name -> callable）
* [ ] 实现 `build_system_prompt()`：把 `{tool_schema}` 替换成 pretty JSON
* [ ] 实现 `run_react()`（原生 tool calling 版本）
* [ ] 实现 `run_react_json()`（JSON fallback 版本）
* [ ] 自动探测：如果服务端返回/接受 tools，则走路线 A；否则走路线 B
* [ ] 加日志：每步打印 step id / tool / args / observation（可选）
