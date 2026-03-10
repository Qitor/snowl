# Snowl Examples Convention

All examples are stored in top-level `examples/` (not under `snowl/`).

Each example should be one folder:

```text
examples/
  <example_name>/
    task.py
    agent.py
    scorer.py
    model.yml      # recommended for provider + agent matrix
    tool.py        # optional
    README.md      # optional but recommended
```

Run an example:

```bash
snowl eval examples/<example_name>
```

Official benchmark examples in this repo:

- `examples/strongreject-official`
- `examples/terminalbench-official`
- `examples/osworld-official`
- `examples/toolemu-official`
- `examples/agentsafetybench-official`

Some benchmark examples depend on reference repos under `references/`, especially:

- `examples/toolemu-official` -> `references/ToolEmu`
- `examples/agentsafetybench-official` -> `references/Agent-SafetyBench`

Variant filtering:

```bash
snowl eval examples/<example_name> --agent <agent_id> --variant <variant_id>
```

Benchmark compare with variants:

```bash
snowl bench run terminalbench --project examples/terminalbench-official --split test --variant v1,v2
```

Live CLI showcase demo:

```bash
snowl eval examples/terminalbench-official --keys "p,p,m,f,r"
```

See [`/Users/morinop/coding/snowl_v2/live_cli_demo.md`](/Users/morinop/coding/snowl_v2/live_cli_demo.md) for the full scripted flow.

Authoring rule (default):

- Keep examples minimal and direct.
- Use decorator-first declarations: `@task`, `@agent`, `@scorer`.
- Prefer factory functions returning objects (or lists) for lazy setup.
- Avoid wrapper classes/functions unless they add real runtime logic
  (e.g., lazy external resource initialization or stateful orchestration).
- Fallback (non-decorator) discovery still works for compatibility.
- For multi-model compare, declare models in `model.yml` under `agent_matrix.models`
  and use `build_model_variants(...)` from `snowl.agents`.
- Keep `judge.model` separate from tested agent models when a scorer uses a judge.
