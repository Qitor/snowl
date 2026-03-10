# strongreject-official

Official StrongReject example using Snowl's YAML-first multi-model authoring.

Files:

- `project.yml`: provider, agent sweep, judge, eval code paths, runtime budgets
- `task.py`: loads StrongReject prompts and wraps them with `AIM.txt`
- `agent.py`: expands one provider into multiple tested models with `build_model_variants(...)`
- `scorer.py`: uses `judge.model` from `project.yml`

Run:

```bash
snowl eval examples/strongreject-official/project.yml
```

Notes:

- `agent_matrix.models` are the tested models
- `judge.model` is the scorer judge model
- one run compares all declared models through `Task x AgentVariant x Sample`
