# Benchmark Catalog

Snowl ships with 28 built-in benchmark adapters spanning agent safety, agent
capability, and cybersecurity domains.

---

## Agent Safety

Benchmarks that evaluate whether agents behave safely, resist manipulation, and
avoid harmful actions.

### StrongReject

| | |
|---|---|
| **Registry name** | `strongreject` |
| **Domain** | Agent safety |
| **Primary metric** | `strongreject` (lower = better) |
| **Description** | Refusal and safety behavior evaluation |
| **Assets** | Bundled CSV dataset |
| **Quick run** | `snowl eval examples/strongreject-official/project.yml` |

### XSTest

| | |
|---|---|
| **Registry name** | `xstest` |
| **Domain** | Agent safety |
| **Primary metric** | `xstest_safety` (higher = better) |
| **Description** | Over-refusal and unsafe-compliance checks |
| **Assets** | Pinned remote asset cache |

### Coconot

| | |
|---|---|
| **Registry name** | `coconot` |
| **Domain** | Agent safety |
| **Primary metric** | `noncompliance_score` (higher = better) |
| **Description** | Compliance/noncompliance safety behavior |
| **Assets** | Bundled dataset |

### FORTRESS

| | |
|---|---|
| **Registry names** | `fortress_adversarial`, `fortress_benign` |
| **Domain** | Agent safety |
| **Primary metrics** | `ARS` (adversarial), `ORS` (benign) |
| **Description** | Benign and adversarial safeguard behavior |

### AgentHarm

| | |
|---|---|
| **Registry names** | `agentharm`, `agentharm_benign` |
| **Domain** | Agent safety |
| **Primary metric** | `agentharm_safety` (higher = better) |
| **Description** | Harmful and benign agent tool-use prompts |
| **Features** | Per-sample tool selection |

### AgentDojo

| | |
|---|---|
| **Registry name** | `agentdojo` |
| **Domain** | Agent safety |
| **Primary metric** | `agentdojo_score` (higher = better) |
| **Description** | Stateful tool-use prompt injection |
| **Suites** | Banking (11 tools), Travel (18 tools) |
| **Features** | StatefulToolExecutor, paired evaluation |
| **Concurrency** | `api_call_amplification=5.0`, `recommended_max_running=6` |

### ToolEmu

| | |
|---|---|
| **Registry name** | `toolemu` |
| **Domain** | Agent safety |
| **Primary metric** | `risk_rate` (lower = better) |
| **Description** | Tool-use safety via LM-emulated execution |
| **Features** | EmulatedToolWrapper, adversarial simulation |
| **Concurrency** | `api_call_amplification=30.0`, `recommended_max_running=3` |
| **Scorer** | Uses provider (LLM-based scoring) |

### Agent-SafetyBench

| | |
|---|---|
| **Registry name** | `agentsafetybench` |
| **Domain** | Agent safety |
| **Primary metric** | `safety_rate` (higher = better) |
| **Description** | Agent safety benchmark integration |

### MASK

| | |
|---|---|
| **Registry name** | `mask` |
| **Domain** | Agent safety |
| **Primary metric** | `mask_score` (lower = better) |
| **Description** | Safety and jailbreak risk evaluation |

### IPI Coding Agent

| | |
|---|---|
| **Registry name** | `ipi_coding_agent` |
| **Domain** | Agent safety |
| **Primary metric** | `ipi_coding_agent_score` (higher = better) |
| **Description** | Coding-agent prompt injection |
| **Features** | Canary, trace, workspace, and checkpoint scoring |

---

## Agent Capability

Benchmarks that evaluate whether agents can correctly use tools and complete tasks.

### BFCL

| | |
|---|---|
| **Registry name** | `bfcl` |
| **Domain** | Agent capability |
| **Primary metric** | `function_call_accuracy` (higher = better) |
| **Description** | Function-calling accuracy |
| **Features** | Dynamic per-sample tools and call matching |

### AgentBench OS

| | |
|---|---|
| **Registry name** | `agent_bench_os` |
| **Domain** | Agent capability |
| **Primary metric** | `agent_bench_os_success` (higher = better) |
| **Description** | OS and terminal-style agent tasks |
| **Features** | Snowl-native answer/check scoring |

---

## Cybersecurity

Benchmarks for cybersecurity knowledge and capability evaluation.

### TerminalBench

| | |
|---|---|
| **Registry name** | `terminalbench` |
| **Domain** | Cyber |
| **Primary metric** | `pass_rate` (higher = better) |
| **Description** | Terminal task execution |
| **Features** | Container-aware execution |

### OSWorld

| | |
|---|---|
| **Registry name** | `osworld` |
| **Domain** | Cyber |
| **Primary metric** | `success_rate` (higher = better) |
| **Description** | GUI desktop tasks |
| **Features** | Runtime-managed GUI container path |
| **Dependencies** | `osworld_eval` extras |

### WMDP

| | |
|---|---|
| **Registry names** | `wmdp-cyber`, `wmdp-chem` |
| **Domain** | Cyber / Chemical |
| **Primary metric** | `accuracy` (higher = better) |
| **Description** | Bio, cyber, and chemical risk knowledge |

### CyberMetric

| | |
|---|---|
| **Registry names** | `cybermetric_80`, `cybermetric_500`, `cybermetric_2000`, `cybermetric_10000` |
| **Domain** | Cyber |
| **Primary metric** | `accuracy` (higher = better) |
| **Description** | Cybersecurity multiple-choice questions |

### SecQA

| | |
|---|---|
| **Registry names** | `sec_qa_v1`, `sec_qa_v2` |
| **Domain** | Cyber |
| **Primary metric** | `accuracy` (higher = better) |
| **Description** | Cybersecurity multiple-choice questions |
| **Assets** | Pinned Hugging Face dataset cache |

### SEVENLLM

| | |
|---|---|
| **Registry names** | `sevenllm_mcq_en`, `sevenllm_mcq_zh` |
| **Domain** | Cyber |
| **Primary metric** | `accuracy` (higher = better) |
| **Description** | Multilingual cybersecurity MCQ (English/Chinese) |

---

## Generic Adapters

For custom datasets without a dedicated adapter.

### JSONL

| | |
|---|---|
| **Registry name** | `jsonl` |
| **Description** | Generic JSONL row adapter |
| **Usage** | Quick adapter authoring for local datasets |

### CSV

| | |
|---|---|
| **Registry name** | `csv` |
| **Description** | Generic CSV row adapter |
| **Usage** | Quick adapter authoring for local datasets |

---

## Running benchmarks

```bash
# List all benchmarks
snowl bench list

# Run a built-in benchmark
snowl bench run strongreject --project ./project.yml --split test --limit 10

# Run with an external adapter
snowl bench run mybench --adapter ./mybench/adapter.py:adapter --project ./project.yml

# Run an example project
snowl eval examples/strongreject-official/project.yml
```

## Running suites

Combine multiple benchmarks into one run:

```yaml
# suite.yml
suite:
  name: safety-smoke
  project: ./project.yml
  split: test
  limit: 10
  benchmarks:
    - name: strongreject
    - name: toolemu
    - name: agentdojo
```

```bash
snowl suite check suite.yml
snowl suite run suite.yml
```
