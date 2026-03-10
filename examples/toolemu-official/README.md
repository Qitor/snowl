# toolemu-official

Official-style ToolEmu example using Snowl's YAML-first multi-model authoring.

Files:

- `project.yml`: provider, tested models, judge model, eval code paths, runtime budgets, toolemu settings
- `task.py`: loads ToolEmu cases from `references/ToolEmu/assets/all_cases.json`
- `agent.py`: builds one tested ToolEmu agent per model entry
- `scorer.py`: uses `judge.model` as the evaluator/support model

Setup:

```bash
git clone https://github.com/ryoungj/ToolEmu.git
git clone https://github.com/dhh1995/PromptCoder.git

cd PromptCoder
pip install -e .
cd ../ToolEmu
pip install -e .
```

Run:

```bash
snowl eval examples/toolemu-official/project.yml
```

Benchmark mode:

```bash
snowl bench run toolemu --project examples/toolemu-official/project.yml --split official
```

Settings live in `project.yml` under `benchmarks.toolemu`, for example:

- `agent_type`
- `simulator_type`
- `max_iterations`
- `verbose`

`agent_matrix.models` are the tested models. `judge.model` is the shared simulator/evaluator support model.
