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

Some examples depend on reference repos under `references/`, especially:

- `toolemu-official` -> `references/ToolEmu`
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
