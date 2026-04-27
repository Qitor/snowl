# Benchmark Taxonomy

## Purpose

This document defines how snowl classifies benchmarks for the risk monitor layer.

## Top-level domains

Recommended initial normalized domains:

- `cyber_offense`
- `biological_risks`
- `chemical_risks`
- `loss_of_control`
- `agentic_safety`
- `cross_domain` (temporary escape hatch only)

## Benchmark types

Allowed values:
- `capability`
- `safety`

## Family examples

- `wmdp`
- `strongreject`
- `mask`
- `cyberseceval2`
- `sosbench`
- `sciknoweval`
- `terminalbench`
- `osworld`
- `toolemu`
- `agentsafetybench`

## Sample preview modes

Allowed values:
- `qa`
- `dialog`
- `tool_trace`
- `gui_trace`
- `code_trace`

## Mapping guidance

### Capability benchmarks
Use when the benchmark measures:
- harmful task completion skill
- scientific or cyber knowledge relevant to risk domains
- attack execution competence
- environment interaction ability

### Safety benchmarks
Use when the benchmark measures:
- refusal behavior
- jailbreak resistance
- honesty or concealment
- oversight resistance
- unsafe tool use behavior

## Initial mapping examples

- `wmdp-cyber` -> `domain=cyber_offense`, `benchmark_type=capability`
- `wmdp-chem` -> `domain=chemical_risks`, `benchmark_type=capability`
- `strongreject` -> `domain=cross_domain`, `benchmark_type=safety`
- `mask` -> `domain=loss_of_control`, `benchmark_type=safety`
- `terminalbench` -> `domain=cyber_offense`, `benchmark_type=capability`
- `toolemu` -> `domain=agentic_safety`, `benchmark_type=safety`

## Important rule

This taxonomy is a backend contract, not only a documentation artifact.
Every registered benchmark should expose this metadata programmatically.
