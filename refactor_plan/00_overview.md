# Snowl Framework Refactor Plan: ToolEmu & AgentDojo Concurrent Evaluation

## Overview

This document series presents a comprehensive analysis and refactoring plan for integrating ToolEmu and AgentDojo benchmarks into the Snowl evaluation framework with high-quality concurrent evaluation capability. The plan is informed by deep analysis of the current Snowl architecture, the reference implementations of both benchmarks, and the design patterns from inspect_evals.

## Document Index

| # | Document | Focus |
|---|----------|-------|
| 01 | [Current Architecture Analysis](01_current_architecture.md) | Snowl's current state: strengths, gaps, and pain points |
| 02 | [Benchmark Integration Deep Dive](02_benchmark_integration.md) | ToolEmu & AgentDojo integration specifics and gaps |
| 03 | [Concurrency Architecture](03_concurrency_architecture.md) | Current concurrency model analysis and improvement plan |
| 04 | [Refactor Implementation Plan](04_refactor_implementation.md) | Phased implementation roadmap with concrete steps |
| 05 | [inspect_evals Reference Patterns](05_inspect_evals_patterns.md) | Key patterns worth borrowing from inspect_evals |

## Key Findings Summary

### Current Strengths
- Solid phase-aware concurrency model (`ResourceScheduler` with trial/scoring/container/provider budgets)
- Clean adapter pattern (`BaseBenchmarkAdapter` template method) enabling 20+ benchmarks
- Rich scorer primitives (`ToolTracePolicyScorer`, `StateTransitionScorer`, `CheckpointScoreScorer`)
- Provider-level admission wired into model client, enabling true API-level throttling
- Auto-retry and recovery mechanisms

### Critical Gaps
1. **Scorer is synchronous** (`scorer.score()` is sync, wrapped via `asyncio.to_thread`), blocking concurrent scoring slots
2. **No sample-level parallelism** - concurrency is at trial level only; ToolEmu's 144 cases and AgentDojo's 97+ tasks all expand into separate trials with no intra-trial parallelism
3. **ToolEmu scorer lacks native emulation integration** - only supports external `evaluate_fn` or naive `tool_trace_policy`, missing LM-emulated sandbox scoring
4. **AgentDojo adapter is dataset-only** - does not leverage AgentDojo's `FunctionsRuntime` for stateful tool execution or attack/defense pipeline
5. **No benchmark-specific concurrency profiles** - `RuntimePolicy` treats both benchmarks as generic "local" tasks
6. **Scorer composition is ad-hoc** - `AgentDojoScorer` instantiates sub-scorers per-call; no shared composition framework
7. **No deferred scoring** - scoring is tightly coupled to execution phase, cannot rescore with different scorers later
8. **Missing evaluation-level aggregation** - no first-class metric aggregation (accuracy, stderr, grouped metrics) at the benchmark level

## Target State

A refactored Snowl framework that:
- Supports **both dataset-level and runtime-level** benchmark integration
- Enables **sample-level parallelism** within a single benchmark run
- Provides **async-native scorers** that participate in scheduler admission
- Offers **benchmark-specific concurrency profiles** for optimal throughput
- Implements **deferred scoring** for iterative scorer development
- Delivers **first-class metric aggregation** with standard errors and grouped breakdowns
