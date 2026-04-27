# Iteration Summary: `risk-monitor-foundation`

## Product objective

Turn **snowl** into a framework that can power an AIRiskMonitor-style display layer by introducing:

1. **benchmark taxonomy**
2. **dashboard-native aggregation artifacts**
3. **domain- and benchmark-aware monitor APIs**
4. **frontend separation between risk dashboard and run operations**

## Why this iteration matters

Today, snowl is already strong as a run/execution framework:
- CLI, monitor, retry, artifacts, compare workflow
- built-in benchmark support
- agent/model sweep capability
- web monitor and run workspace

But its outputs are still primarily:
- run-centric
- experiment-centric
- matrix-centric

That is not enough for a risk-monitor product layer.

## Core shift

The key architectural shift for this iteration is:

- from **Run -> Summary -> Matrix**
- to **Run -> Benchmark Summary -> Domain Summary -> Leaderboard Rows -> Risk Dashboard**

## Required implementation outcome

At the end of this iteration, snowl should be able to do all of the following:

- assign every benchmark to a domain and benchmark type
- emit benchmark/domain rollups as first-class artifacts
- expose risk-focused APIs without breaking run-focused APIs
- render `/` as a risk-monitor homepage
- preserve `/runs` as the operator-facing execution monitor
- support filters like company, country, source type, reasoning, model family
- onboard a first batch of benchmarks suited for portfolio-style risk display

## Out of scope

This iteration should not try to solve everything at once.

Do not turn this into:
- a full runtime rewrite
- a scheduler redesign project
- a generic multi-provider abstraction overhaul
- a giant benchmark ingestion sprint

The point is to unlock the **risk-monitor data plane** first.
