# Snowl Examples Convention

All examples live in top-level `examples/`.

Recommended layout:

```text
examples/
  <example_name>/
    project.yml
    task.py
    agent.py
    scorer.py
    tool.py        # optional
    README.md      # recommended
```

Run an example:

```bash
snowl eval examples/<example_name>/project.yml
```

Official benchmark examples in this repo:

- `examples/strongreject-official`
- `examples/terminalbench-official`
- `examples/osworld-official`
- `examples/toolemu-official`
- `examples/agentsafetybench-official`
- `examples/safety-benchmark-smoke`

Agent wrapper snippets live under `examples/agents/`. They are intentionally
small files for adapting your own async agent, OpenAI SDK loop, or LangGraph app
to Snowl's `agent_id` + async `run(state, context, tools=None)` contract.

Some examples depend on static benchmark data or environment assets under `references/`, especially:

- `agentsafetybench-official` -> `references/Agent-SafetyBench`
- `terminalbench-official` -> `references/terminal-bench`
- `osworld-official` -> `references/OSWorld`

Authoring rules:

- `project.yml` is the source of truth
- `eval.code.base_dir` plus module paths explicitly point to `task.py`, `agent.py`, `scorer.py`, and optional `tool.py`
- keep tested models under `agent_matrix.models`
- keep `judge.model` separate from tested models when a scorer uses a judge
- prefer `build_model_variants(...)` for multi-model examples

Variant filtering:

```bash
snowl eval examples/<example_name>/project.yml --agent <agent_id> --variant <variant_id>
```

Benchmark adapter mode:

```bash
snowl bench run terminalbench --project examples/terminalbench-official/project.yml --split test --variant qwen25_7b
```

Remote safety benchmark smoke testing:

```bash
export SNOWL_SMOKE_API_KEY=...
snowl bench run coconot --project examples/safety-benchmark-smoke --split test --limit 1
snowl bench run xstest --project examples/safety-benchmark-smoke --split test --limit 1 --adapter-arg subset=unsafe
snowl bench run cybermetric_80 --project examples/safety-benchmark-smoke --split test --limit 2
```
