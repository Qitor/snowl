# Codex Best Practices For Snowl

Last reviewed: 2026-03-10

This document adapts official Codex guidance to the `snowl` repository.
It is meant to help humans write better Codex tasks and to help coding agents operate consistently in this codebase.

## Official References

The guidance here is based on OpenAI materials:

- [How OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)
- [Introducing Codex](https://openai.com/index/introducing-codex/)
- [Using PLANS.md for multi-hour problem solving](https://developers.openai.com/cookbook/articles/codex_exec_plans)
- [OpenAI developer docs landing page](https://developers.openai.com/)

Key takeaways from those sources:

1. Codex performs better with strong repo-local guidance such as `AGENTS.md`.
2. Large tasks should begin with a planning phase and a living `PLANS.md`.
3. Prompts work better when written like GitHub issues with file paths, constraints, and expected outcomes.
4. Better environment setup reduces agent error rate substantially.
5. Codex works best on well-scoped tasks with clear verification.

## What This Means In Snowl

Snowl is a medium-complexity repo with multiple subsystems and mirrored Web UI packaging.
That makes context discipline especially important.

### Always provide these when assigning a task

1. Goal
2. Constraints
3. Relevant files or directories
4. Required validation
5. What should not change

Good example:

```text
Goal: improve experiment summary aggregation for multi-agent compare.
Files: snowl/aggregator/summary.py, snowl/web/monitor.py, tests/test_aggregator_summary.py
Constraints: do not change task result schema; do not redesign UI.
Validation: pytest -q tests/test_aggregator_summary.py tests/test_eval_web_observability.py
```

## Use Planning Deliberately

Use `PLANS.md` when a task is:

- cross-cutting
- likely to take more than one substantial implementation pass
- likely to involve architecture, contracts, docs, and tests together

Do not skip planning for:

- runtime refactors
- artifact schema changes
- Web monitor contract changes
- packaging/install behavior changes

## Keep Tasks Narrow

Snowl has enough moving parts that broad prompts create noisy results.
Prefer:

- one runtime issue
- one benchmark adapter bug
- one Web monitor contract change
- one packaging/install improvement

Avoid combining:

- benchmark logic changes
- runtime schema changes
- frontend redesign
- packaging changes

unless the task explicitly requires all of them.

## Treat Environment Setup As Part Of The Work

OpenAI's guidance emphasizes development-environment quality.
For Snowl, that means the following should be assumed or made explicit:

- `pip install -e .`
- Node LTS is available for `webui`
- benchmark reference repos under `references/`
- Docker availability when working on container-heavy benchmarks

If a task depends on any of these, say so in the prompt.

## Prefer Verifiable Outcomes

Codex is most useful when success can be checked.
For Snowl, valid verification targets include:

- a focused `pytest` subset
- `snowl eval examples/<name>`
- `snowl bench run ...`
- `cd webui && npm run -s typecheck`
- a concrete monitor URL or artifact file path

Avoid prompts that only ask for "cleanup", "improve architecture", or "make it better" without observable outputs.

## Repo-Specific Execution Rules

### Web UI

- edit `webui/` as the primary source
- do not hand-edit `.next/`
- sync intentional source changes to `snowl/_webui/` when packaging behavior depends on that mirror

### Benchmarks

- do not modify `references/` unless the task explicitly targets reference setup
- prefer fixing adapters in `snowl/benchmarks/` over patching example projects

### Runtime

- keep provider quirks and runtime quirks inside the correct layer
- preserve strict normalization boundaries
- do not let UI convenience weaken artifact or event contracts

## Recommended Prompt Template For Snowl

Use this structure for future Codex tasks:

```text
Read first:
- AGENTS.md
- START_HERE.md
- PLANS.md
- any subsystem docs relevant to the task

Goal:
<one clear outcome>

Why it matters:
<user-visible or platform-visible reason>

Relevant files:
- <path>
- <path>

Constraints:
- <do not change X>
- <keep Y strict>

Validation:
- <exact command>
- <exact scenario>

Output:
- summarize root cause
- summarize files changed
- summarize validation honestly
```

## When To Ask Codex For Design First

Ask for design or repo reading first when:

- the task spans runtime plus UI
- the task changes contracts
- the task changes packaging or install behavior
- the task affects multiple benchmark families

In those cases, ask Codex to:

1. read the relevant docs and code
2. summarize current architecture
3. identify risks
4. propose a scoped implementation plan

Then move to implementation.

## What Good Codex Contributions Look Like In Snowl

1. They strengthen shared contracts instead of adding special cases.
2. They improve observability alongside behavior changes.
3. They leave tests and docs in better shape.
4. They are honest about what was and was not validated.
5. They preserve the repo's long-term direction toward a real evaluation platform.
