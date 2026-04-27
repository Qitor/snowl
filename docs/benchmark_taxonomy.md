# Benchmark Taxonomy

## Purpose

This document defines how Snowl classifies benchmarks for the evaluation dashboard.

## Top-level domains

| Domain | Description |
|--------|-------------|
| `cyber_offense` | Cybersecurity and offensive computing capabilities |
| `biological_risks` | Biological threat-related capabilities |
| `chemical_risks` | Chemistry and chemical safety |
| `loss_of_control` | AI control and alignment risks |
| `agentic_safety` | Agent safety, deception, and tool misuse |
| `cross_domain` | Benchmarks spanning multiple domains (temporary escape hatch) |
| `uncategorized` | Default for benchmarks without domain assignment |

## Benchmark types

| Type | Description |
|------|-------------|
| `capability` | Measures harmful task completion skill, knowledge, or environment interaction ability |
| `safety` | Measures refusal behavior, jailbreak resistance, honesty, or unsafe tool use |

## Sample preview modes

| Mode | Description | Used by |
|------|-------------|---------|
| `qa` | Question-answer format with choices | WMDP, MCQ benchmarks |
| `dialog` | Conversation preview with turns | StrongReject, MASK, AgentSafetyBench |
| `tool_trace` | Action/observation log | ToolEmu |
| `gui_trace` | Desktop/GUI interaction log | OSWorld |
| `code_trace` | Terminal/code execution log | TerminalBench |

## Current benchmark mapping

| Benchmark | Domain | Type | Family | Primary Metric | Higher is Better | Preview Mode |
|-----------|--------|------|--------|----------------|-----------------|-------------|
| strongreject | agentic_safety | safety | strongreject | strongreject | No | dialog |
| terminalbench | cyber_offense | capability | terminalbench | pass_rate | Yes | code_trace |
| osworld | cyber_offense | capability | osworld | success_rate | Yes | gui_trace |
| toolemu | agentic_safety | safety | toolemu | risk_rate | No | tool_trace |
| agentsafetybench | agentic_safety | safety | agentsafetybench | safety_rate | Yes | dialog |
| wmdp-cyber | cyber_offense | capability | wmdp | accuracy | Yes | qa |
| wmdp-chem | chemical_risks | capability | wmdp | accuracy | Yes | qa |
| mask | agentic_safety | safety | mask | mask_score | No | dialog |

## Important rule

This taxonomy is a backend contract, not only a documentation artifact. Every registered benchmark must expose this metadata programmatically via `BenchmarkInfo` and the `benchmark_info()` adapter hook.
